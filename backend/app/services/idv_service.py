import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.document import Document, DocumentType
from app.models.face_verification import FaceVerification
from app.models.idv_application import ApplicationStatus, IDVApplication
from app.utils.storage import get_storage
from app.utils.validators import ValidationError, validate_uploaded_image

_CELERY_AVAILABLE = True
try:
    from app.tasks.verification import (
        process_document_ocr,
        process_face_comparison,
        process_fraud_check,
        run_god_pipeline,
    )
except Exception:
    _CELERY_AVAILABLE = False

settings = get_settings()
logger = structlog.get_logger()

MIME_TO_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


class IDVServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code


async def create_application(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> IDVApplication:
    """Create a new IDV application for the user."""
    result = await db.execute(
        select(IDVApplication).where(
            IDVApplication.user_id == user_id,
            IDVApplication.status.in_(
                [
                    ApplicationStatus.PENDING,
                    ApplicationStatus.PROCESSING,
                    ApplicationStatus.READY_FOR_REVIEW,
                ]
            ),
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise IDVServiceError("You already have an active IDV application", status_code=409)

    application = IDVApplication(user_id=user_id, status=ApplicationStatus.PENDING)
    db.add(application)
    await db.flush()
    await db.refresh(application)

    await logger.ainfo(
        "IDV application created",
        application_id=str(application.id),
        user_id=str(user_id),
    )
    return application


async def get_user_application(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> IDVApplication | None:
    """Get the most recent IDV application for a user, with all related data."""
    result = await db.execute(
        select(IDVApplication)
        .where(IDVApplication.user_id == user_id)
        .options(
            selectinload(IDVApplication.documents),
            selectinload(IDVApplication.face_verifications),
        )
        .order_by(IDVApplication.created_at.desc())
    )
    return result.scalar_one_or_none()


async def get_application_by_id(
    db: AsyncSession,
    application_id: uuid.UUID,
) -> IDVApplication | None:
    """Get a specific IDV application by ID with all related data."""
    result = await db.execute(
        select(IDVApplication)
        .where(IDVApplication.id == application_id)
        .options(
            selectinload(IDVApplication.documents),
            selectinload(IDVApplication.face_verifications),
            selectinload(IDVApplication.user),
        )
    )
    return result.scalar_one_or_none()


def _extract_document_fields_sync(abs_path: str, doc_type: str) -> dict:
    """Run synchronous OCR extraction and return structured fields dict.

    Called via asyncio.to_thread so it doesn't block the event loop.
    Returns empty dict on any error — callers treat it as best-effort.
    """
    try:
        from app.services.ocr_service import extract_text, get_raw_text
        from app.services.pipeline.stage_2_extraction import (
            extract_national_id_front,
            extract_passport_mrz_td3,
            extract_passport_viz,
        )

        ocr_results = extract_text(abs_path)
        raw_text = get_raw_text(ocr_results)

        if doc_type == "passport":
            mrz = extract_passport_mrz_td3(raw_text, ocr_results)
            viz = extract_passport_viz(raw_text, ocr_results)
            # MRZ is authoritative; VIZ fills gaps
            if not mrz.full_name and viz.full_name:
                mrz.full_name = viz.full_name
            if not mrz.dob and viz.dob:
                mrz.dob = viz.dob
            if not mrz.document_number and viz.document_number:
                mrz.document_number = viz.document_number
            if not mrz.expiry_date and viz.expiry_date:
                mrz.expiry_date = viz.expiry_date
            if viz.place_of_birth:
                mrz.place_of_birth = viz.place_of_birth
            if viz.issuing_authority:
                mrz.issuing_authority = viz.issuing_authority
            fields = mrz
        else:
            fields = extract_national_id_front(raw_text, ocr_results)

        return {
            "document_type": doc_type,
            "full_name": fields.full_name,
            "dob": fields.dob,
            "document_number": fields.document_number,
            "expiry_date": fields.expiry_date,
            "nationality": fields.nationality,
            "gender": fields.gender,
            "national_id_number": fields.national_id_number,
            "father_name": fields.father_name,
            "place_of_birth": fields.place_of_birth,
            "issuing_authority": fields.issuing_authority,
            "confidences": fields.confidences,
            "raw_text": raw_text[:1000],
        }
    except Exception as exc:
        logger.warning("Sync OCR extraction failed", error=str(exc), doc_type=doc_type)
        return {}


async def upload_document(
    db: AsyncSession,
    application_id: uuid.UUID,
    user_id: uuid.UUID,
    doc_type: str,
    file_content: bytes,
    original_filename: str,
) -> Document:
    """Upload and validate an ID document for a IDV application."""
    await _get_and_validate_application(db, application_id, user_id)

    try:
        mime_type, width, height = validate_uploaded_image(file_content)
    except ValidationError as e:
        raise IDVServiceError(e.detail, status_code=422) from None

    storage = get_storage()
    extension = MIME_TO_EXTENSION.get(mime_type, ".jpg")
    relative_path = await storage.save_file(
        file_content,
        subdir=f"documents/{application_id}",
        extension=extension,
    )

    document = Document(
        application_id=application_id,
        doc_type=DocumentType(doc_type),
        file_path=relative_path,
        original_filename=original_filename,
        file_size=len(file_content),
        mime_type=mime_type,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)

    await logger.ainfo(
        "Document uploaded",
        document_id=str(document.id),
        application_id=str(application_id),
        doc_type=doc_type,
        size=len(file_content),
    )

    abs_path = storage.get_absolute_path(relative_path)

    # Queue OCR + fraud detection as Celery tasks (async — returns immediately)
    if _CELERY_AVAILABLE:
        try:
            process_document_ocr.delay(str(document.id), abs_path, doc_type)
            process_fraud_check.delay(str(document.id), abs_path)
        except Exception as e:
            await logger.awarning("Failed to dispatch tasks", error=str(e))

    return document


async def upload_selfie(
    db: AsyncSession,
    application_id: uuid.UUID,
    user_id: uuid.UUID,
    file_content: bytes,
    original_filename: str,
) -> FaceVerification:
    """Upload a selfie for face matching."""
    await _get_and_validate_application(db, application_id, user_id)

    try:
        mime_type, width, height = validate_uploaded_image(file_content)
    except ValidationError as e:
        raise IDVServiceError(e.detail, status_code=422) from None

    storage = get_storage()
    extension = MIME_TO_EXTENSION.get(mime_type, ".jpg")
    relative_path = await storage.save_file(
        file_content,
        subdir=f"selfies/{application_id}",
        extension=extension,
    )

    face_verification = FaceVerification(
        application_id=application_id,
        selfie_path=relative_path,
    )
    db.add(face_verification)
    await db.flush()
    await db.refresh(face_verification)

    await logger.ainfo(
        "Selfie uploaded",
        verification_id=str(face_verification.id),
        application_id=str(application_id),
    )

    # Dispatch verification pipeline(s) based on pipeline_mode
    if _CELERY_AVAILABLE:
        mode = settings.pipeline_mode

        # Legacy pipeline: face comparison task
        if mode in ("legacy", "both"):
            selfie_abs_path = storage.get_absolute_path(relative_path)
            doc_result = await db.execute(
                select(Document).where(Document.application_id == application_id).order_by(Document.uploaded_at.desc())
            )
            latest_doc = doc_result.scalar_one_or_none()
            if latest_doc:
                doc_abs_path = storage.get_absolute_path(latest_doc.file_path)
                try:
                    process_face_comparison.delay(str(application_id), selfie_abs_path, doc_abs_path)
                    await logger.ainfo(
                        "Legacy face comparison task dispatched",
                        application_id=str(application_id),
                    )
                except Exception as e:
                    await logger.awarning("Failed to dispatch face comparison", error=str(e))

        # God pipeline: full 10-stage verification
        if mode in ("god", "both"):
            try:
                run_god_pipeline.delay(str(application_id))
                await logger.ainfo(
                    "God pipeline task dispatched",
                    application_id=str(application_id),
                )
            except Exception as e:
                await logger.awarning("Failed to dispatch god pipeline", error=str(e))

        # Update application status to processing
        app_result = await db.execute(select(IDVApplication).where(IDVApplication.id == application_id))
        application = app_result.scalar_one_or_none()
        if application and application.status == ApplicationStatus.PENDING:
            application.status = ApplicationStatus.PROCESSING
            await db.flush()

    return face_verification


async def _get_and_validate_application(
    db: AsyncSession,
    application_id: uuid.UUID,
    user_id: uuid.UUID,
) -> IDVApplication:
    """Fetch and validate that the application belongs to the user and is editable."""
    result = await db.execute(select(IDVApplication).where(IDVApplication.id == application_id))
    application = result.scalar_one_or_none()

    if not application:
        raise IDVServiceError("Application not found", status_code=404)
    if application.user_id != user_id:
        raise IDVServiceError("Not authorized to modify this application", status_code=403)
    if application.status not in (ApplicationStatus.PENDING, ApplicationStatus.ERROR):
        raise IDVServiceError("Application cannot be modified in its current state", status_code=409)

    return application

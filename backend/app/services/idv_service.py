import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.audit_log import AuditLog
from app.models.document import Document, DocumentType
from app.models.face_verification import FaceVerification
from app.models.idv_application import ApplicationStatus, IDVApplication
from app.models.pipeline_result import PipelineResult
from app.models.task_outbox import TaskOutbox
from app.services.task_outbox import enqueue
from app.utils.storage import get_storage
from app.utils.validators import ValidationError, validate_uploaded_image

settings = get_settings()
MIME_TO_EXTENSION = {"image/jpeg": ".jpg", "image/png": ".png"}


class IDVServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code


async def create_application(db: AsyncSession, user_id: uuid.UUID) -> IDVApplication:
    existing = await db.execute(
        select(IDVApplication)
        .where(
            IDVApplication.user_id == user_id,
            IDVApplication.status.in_(
                [
                    ApplicationStatus.PENDING,
                    ApplicationStatus.PROCESSING,
                    ApplicationStatus.READY_FOR_REVIEW,
                    ApplicationStatus.ERROR,
                ]
            ),
        )
        .limit(1)
    )
    if existing.scalar_one_or_none():
        raise IDVServiceError("You already have an active IDV application", status_code=409)
    application = IDVApplication(user_id=user_id, status=ApplicationStatus.PENDING)
    db.add(application)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise IDVServiceError("You already have an active IDV application", status_code=409) from exc
    await db.refresh(application)
    return application


async def get_user_application(db: AsyncSession, user_id: uuid.UUID) -> IDVApplication | None:
    result = await db.execute(
        select(IDVApplication)
        .where(IDVApplication.user_id == user_id)
        .options(selectinload(IDVApplication.documents), selectinload(IDVApplication.face_verifications))
        .order_by(IDVApplication.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_application_by_id(db: AsyncSession, application_id: uuid.UUID) -> IDVApplication | None:
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


def _validate(content: bytes) -> str:
    try:
        mime, _, _ = validate_uploaded_image(content)
        return mime
    except ValidationError as exc:
        raise IDVServiceError(exc.detail, status_code=422) from exc


async def upload_document(
    db: AsyncSession,
    application_id: uuid.UUID,
    user_id: uuid.UUID,
    doc_type: str,
    file_content: bytes,
    original_filename: str,
    replace_existing: bool = False,
) -> Document:
    await _get_and_validate_application(db, application_id, user_id)
    mime = _validate(file_content)
    duplicate = await db.execute(
        select(Document).where(
            Document.application_id == application_id,
            Document.doc_type == DocumentType(doc_type),
        )
    )
    previous = duplicate.scalar_one_or_none()
    if previous and not replace_existing:
        raise IDVServiceError("This document type has already been uploaded", status_code=409)
    storage = get_storage()
    relative_path = await storage.save_file(file_content, f"documents/{application_id}", MIME_TO_EXTENSION[mime])
    if previous:
        # A fresh ID prevents an older OCR task from overwriting the replacement.
        await db.delete(previous)
    document = Document(
        application_id=application_id,
        doc_type=DocumentType(doc_type),
        file_path=relative_path,
        original_filename=original_filename,
        file_size=len(file_content),
        mime_type=mime,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)
    if previous:
        db.add(
            AuditLog(
                application_id=application_id,
                performed_by=user_id,
                action="document_replaced",
                details={
                    "doc_type": doc_type,
                    "previous_document_id": str(previous.id),
                    "document_id": str(document.id),
                },
            )
        )
    absolute = storage.get_absolute_path(relative_path)
    enqueue(db, "app.tasks.verification.process_document_ocr", str(document.id), absolute, doc_type)
    enqueue(db, "app.tasks.verification.process_fraud_check", str(document.id), absolute)
    return document


async def upload_selfie(
    db: AsyncSession,
    application_id: uuid.UUID,
    user_id: uuid.UUID,
    file_content: bytes,
    original_filename: str,
    frame_contents: list[bytes] | None = None,
) -> FaceVerification:
    application = await _get_and_validate_application(db, application_id, user_id)
    documents = (await db.execute(select(Document).where(Document.application_id == application_id))).scalars().all()
    if not any(doc.doc_type in (DocumentType.PASSPORT, DocumentType.NATIONAL_ID) for doc in documents):
        raise IDVServiceError("Upload an identity document before your selfie", status_code=409)
    contents = [file_content, *(frame_contents or [])]
    if len(contents) > 10 or (len(contents) > 1 and len(contents) < 3):
        raise IDVServiceError("Submit one photo for review or 3–10 camera frames", status_code=422)
    if sum(map(len, contents)) > settings.max_file_size_bytes:
        raise IDVServiceError("Combined selfie payload exceeds the upload limit", status_code=413)
    mimes = [_validate(content) for content in contents]
    storage = get_storage()
    paths = []
    for content, mime in zip(contents, mimes, strict=True):
        paths.append(await storage.save_file(content, f"selfies/{application_id}", MIME_TO_EXTENSION[mime]))
    verification = FaceVerification(application_id=application_id, selfie_path=paths[0], frame_paths=paths)
    db.add(verification)
    application.status = ApplicationStatus.PROCESSING
    await db.flush()
    await db.refresh(verification)
    enqueue(db, "app.tasks.verification.run_god_pipeline", str(application_id))
    return verification


async def reset_verification(db: AsyncSession, application_id: uuid.UUID, user_id: uuid.UUID) -> IDVApplication:
    try:
        application = await db.scalar(
            select(IDVApplication).where(IDVApplication.id == application_id).with_for_update(nowait=True)
        )
    except DBAPIError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) != "55P03":
            raise
        raise IDVServiceError("Verification is busy. Wait for processing to finish before resetting.", 409) from exc
    if not application:
        raise IDVServiceError("Application not found", 404)
    if application.user_id != user_id:
        raise IDVServiceError("Not authorized to reset this application", 403)
    if application.status == ApplicationStatus.PROCESSING:
        raise IDVServiceError("Wait for processing to finish before resetting.", 409)
    documents = (await db.execute(select(Document).where(Document.application_id == application_id))).scalars().all()
    selfies = (
        (await db.execute(select(FaceVerification).where(FaceVerification.application_id == application_id)))
        .scalars()
        .all()
    )
    paths = {path for doc in documents for path in (doc.file_path, doc.face_image_path) if path}
    for selfie in selfies:
        paths.update(selfie.frame_paths or [selfie.selfie_path])
        paths.add(selfie.selfie_path)
        if selfie.document_face_path:
            paths.add(selfie.document_face_path)
    old_ids = [str(application_id), *(str(doc.id) for doc in documents)]
    await db.execute(delete(TaskOutbox).where(TaskOutbox.args[0].astext.in_(old_ids)))
    await db.execute(delete(PipelineResult).where(PipelineResult.application_id == application_id))
    await db.execute(delete(IDVApplication).where(IDVApplication.id == application_id))
    fresh = await create_application(db, user_id)
    await db.commit()
    storage = get_storage()
    for path in paths:
        await storage.delete_file(path)
    await storage.delete_application_files(application_id)
    return fresh


async def _get_and_validate_application(db: AsyncSession, application_id: uuid.UUID, user_id: uuid.UUID):
    result = await db.execute(select(IDVApplication).where(IDVApplication.id == application_id).with_for_update())
    application = result.scalar_one_or_none()
    if not application:
        raise IDVServiceError("Application not found", status_code=404)
    if application.user_id != user_id:
        raise IDVServiceError("Not authorized to modify this application", status_code=403)
    if application.status not in (ApplicationStatus.PENDING, ApplicationStatus.ERROR):
        raise IDVServiceError("Application cannot be modified in its current state", status_code=409)
    return application

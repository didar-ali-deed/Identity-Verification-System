import secrets
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.config import get_settings
from app.models.idv_application import ApplicationStatus, IDVApplication
from app.models.user import User
from app.schemas.document import DocumentUploadResponse
from app.schemas.idv import IDVStatusResponse
from app.services.idv_service import (
    IDVServiceError,
    create_application,
    get_user_application,
    reset_verification,
    upload_document,
    upload_selfie,
)
from app.services.pipeline.serialization import serialize_result

settings = get_settings()
router = APIRouter(prefix="/idv", tags=["IDV"])

# Mobile selfie token TTL (10 minutes)
_MOBILE_TOKEN_TTL = 600


@router.post("/reset", response_model=IDVStatusResponse, status_code=201)
async def reset_application(
    application_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    try:
        fresh = await reset_verification(db, application_id, current_user.id)
        return {"id": fresh.id, "status": fresh.status.value, "submitted_at": fresh.submitted_at, "documents": []}
    except IDVServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


@router.post("/submit", response_model=IDVStatusResponse, status_code=201)
async def submit_application(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        application = await create_application(db=db, user_id=current_user.id)
        return {
            "id": application.id,
            "status": application.status.value,
            "submitted_at": application.submitted_at,
            "documents": [],
        }
    except IDVServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None


@router.get("/status", response_model=IDVStatusResponse)
async def get_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    application = await get_user_application(db=db, user_id=current_user.id)
    if not application:
        raise HTTPException(status_code=404, detail="No IDV application found")

    face_score = None
    face_match = None
    if application.face_verifications:
        latest = application.face_verifications[-1]
        face_score = latest.similarity_score
        face_match = latest.is_match

    return {
        "id": application.id,
        "status": application.status.value,
        "submitted_at": application.submitted_at,
        "reviewed_at": application.reviewed_at,
        "rejection_reason": application.rejection_reason,
        "documents": application.documents,
        "face_match_score": face_score,
        "face_is_match": face_match,
        "selfie_uploaded": bool(application.face_verifications),
    }


@router.post("/upload-document", response_model=DocumentUploadResponse, status_code=201)
async def upload_doc(
    application_id: uuid.UUID,
    doc_type: str,
    file: UploadFile,
    replace_existing: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if doc_type not in ("passport", "national_id", "drivers_license"):
        raise HTTPException(
            status_code=422,
            detail="Invalid document type. Must be: passport, national_id, or drivers_license",
        )

    file_content = await file.read(settings.max_file_size_bytes + 1)
    if len(file_content) > settings.max_file_size_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the upload limit")
    if not file_content:
        raise HTTPException(status_code=422, detail="Empty file uploaded")

    try:
        document = await upload_document(
            db=db,
            application_id=application_id,
            user_id=current_user.id,
            doc_type=doc_type,
            file_content=file_content,
            original_filename=file.filename or "unknown",
            replace_existing=replace_existing,
        )
        return {
            "id": document.id,
            "application_id": document.application_id,
            "doc_type": document.doc_type.value,
            "original_filename": document.original_filename,
            "file_size": document.file_size,
            "mime_type": document.mime_type,
            "uploaded_at": document.uploaded_at,
            "extracted_fields": None,  # populated async by Celery
        }
    except IDVServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None


@router.get("/document/{doc_id}")
async def get_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Poll for OCR results on a specific document."""
    from sqlalchemy import select as sa_select

    from app.models.document import Document as DocumentModel

    result = await db.execute(
        sa_select(DocumentModel)
        .join(IDVApplication, DocumentModel.application_id == IDVApplication.id)
        .where(DocumentModel.id == doc_id, IDVApplication.user_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "doc_type": doc.doc_type.value,
        "ocr_ready": doc.ocr_data is not None,
        "extracted_fields": doc.ocr_data,
    }


@router.post("/upload-selfie", status_code=201)
async def upload_selfie_endpoint(
    application_id: uuid.UUID,
    file: UploadFile,
    frames: list[UploadFile] | None = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    contents = await _read_selfie_files(file, frames)

    try:
        verification = await upload_selfie(
            db=db,
            application_id=application_id,
            user_id=current_user.id,
            file_content=contents[0],
            frame_contents=contents[1:],
            original_filename=file.filename or "selfie",
        )
        return {
            "id": verification.id,
            "application_id": verification.application_id,
            "selfie_path": verification.selfie_path,
            "created_at": verification.created_at,
        }
    except IDVServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None


@router.get("/pipeline-result")
async def get_pipeline_result(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get the pipeline result for the current user's most recent application."""
    result = await db.execute(
        select(IDVApplication)
        .where(IDVApplication.user_id == current_user.id)
        .options(selectinload(IDVApplication.pipeline_result))
        .order_by(IDVApplication.created_at.desc())
        .limit(1)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=404, detail="No IDV application found")

    if not application.pipeline_result:
        return {
            "application_id": application.id,
            "pipeline_version": application.pipeline_version,
            "pipeline_decision": application.pipeline_decision,
            "pipeline_result": None,
        }

    pr = application.pipeline_result
    return {
        "application_id": application.id,
        "pipeline_version": pr.pipeline_version,
        "pipeline_decision": pr.final_decision,
        "weighted_total": pr.weighted_total,
        "channel_scores": {
            "A": pr.channel_a_score,
            "B": pr.channel_b_score,
            "C": pr.channel_c_score,
            "D": pr.channel_d_score,
            "E": pr.channel_e_score,
        },
        "decision_override": pr.decision_override,
        "flags": pr.flags,
        "reason_codes": pr.reason_codes,
        "started_at": pr.started_at,
        "completed_at": pr.completed_at,
        "stage_results": pr.stage_results,
        "pipeline_result": serialize_result(pr),
    }


@router.get("/mobile-selfie-token")
async def get_mobile_selfie_token(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a short-lived token so the user can upload a selfie from their phone."""
    application = await get_user_application(db=db, user_id=current_user.id)
    if not application:
        raise HTTPException(status_code=404, detail="No active IDV application found")
    if application.status not in (ApplicationStatus.PENDING, ApplicationStatus.ERROR):
        raise HTTPException(status_code=409, detail="Application is no longer editable")

    token = secrets.token_urlsafe(32)

    r = aioredis.from_url(settings.redis_url)
    try:
        await r.setex(
            f"mobile_selfie:{token}",
            _MOBILE_TOKEN_TTL,
            f"{application.id}:{current_user.id}",
        )
    finally:
        await r.aclose()

    return {"token": token, "expires_in": _MOBILE_TOKEN_TTL}


@router.post("/mobile-upload/{token}", status_code=201)
async def mobile_upload_selfie(
    token: str,
    file: UploadFile,
    frames: list[UploadFile] | None = File(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Accept a selfie upload from a phone using a one-time token (no JWT needed)."""
    contents = await _read_selfie_files(file, frames)
    r = aioredis.from_url(settings.redis_url)
    try:
        value = await r.getdel(f"mobile_selfie:{token}")
        if not value:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
    finally:
        await r.aclose()

    app_id_str, user_id_str = value.decode().split(":")

    try:
        verification = await upload_selfie(
            db=db,
            application_id=uuid.UUID(app_id_str),
            user_id=uuid.UUID(user_id_str),
            file_content=contents[0],
            frame_contents=contents[1:],
            original_filename=file.filename or "selfie",
        )
        return {
            "id": verification.id,
            "application_id": verification.application_id,
            "selfie_path": verification.selfie_path,
            "created_at": verification.created_at,
        }
    except IDVServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None


async def _read_selfie_files(file: UploadFile, frames: list[UploadFile] | None) -> list[bytes]:
    uploads = [file, *(frames or [])]
    if len(uploads) > 10 or len(uploads) == 2:
        raise HTTPException(status_code=422, detail="Submit one photo or 3–10 frames")
    contents = []
    remaining = settings.max_file_size_bytes
    for upload in uploads:
        content = await upload.read(remaining + 1)
        if len(content) > remaining:
            raise HTTPException(status_code=413, detail="Combined selfie payload exceeds the upload limit")
        if not content:
            raise HTTPException(status_code=422, detail="Empty selfie frame")
        contents.append(content)
        remaining -= len(content)
    return contents

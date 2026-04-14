import asyncio
import uuid
from datetime import UTC

import structlog
from celery.signals import worker_process_init

from app.config import get_settings
from app.tasks import celery_app

settings = get_settings()
logger = structlog.get_logger()


@worker_process_init.connect
def _dispose_db_pool(**_kwargs):
    """Dispose asyncpg connections inherited from the parent process after fork.

    Without this, connections created in the parent's event loop are unusable
    in the forked worker's new event loop, causing
    'Future attached to a different loop' errors.
    """
    from app.database import engine  # noqa: PLC0415

    asyncio.run(engine.dispose())


def _run_async(coro):
    """Run an async coroutine from a sync Celery task.

    Uses asyncio.run() which creates a fresh event loop for every call,
    ensuring no cross-loop asyncpg connection leakage.
    """
    return asyncio.run(coro)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_ocr(self, document_id: str, image_path: str, doc_type: str):
    """Run OCR on an uploaded document and store extracted data."""
    try:
        from app.services.ocr_service import extract_text, get_raw_text, parse_document

        logger.msg("Starting OCR processing", document_id=document_id)

        ocr_results = extract_text(image_path)
        raw_text = get_raw_text(ocr_results)
        parsed_data = parse_document(raw_text, ocr_results, doc_type, image_path=image_path)

        # Update document in DB
        _run_async(_update_document_ocr(document_id, parsed_data, raw_text))

        logger.msg("OCR processing complete", document_id=document_id)
        return {"document_id": document_id, "status": "completed", "parsed_data": parsed_data}

    except Exception as exc:
        logger.error("OCR processing failed", document_id=document_id, error=str(exc))
        raise self.retry(exc=exc) from exc


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_face_comparison(self, application_id: str, selfie_path: str, document_image_path: str):
    """Compare face in selfie with face in document."""
    try:
        from app.services.face_service import compare_faces, save_extracted_face

        logger.msg("Starting face comparison", application_id=application_id)

        # Extract face from document
        doc_face_path = document_image_path.replace(".", "_face.")
        face_found = save_extracted_face(document_image_path, doc_face_path)

        if not face_found:
            result = {
                "similarity_score": 0.0,
                "is_match": False,
                "model": "none",
                "error": "No face detected in document",
            }
        else:
            result = compare_faces(doc_face_path, selfie_path)

        # Update face verification in DB
        _run_async(
            _update_face_verification(
                application_id,
                result.get("similarity_score", 0.0),
                result.get("is_match", False),
                result.get("model", "Facenet"),
                doc_face_path if face_found else None,
            )
        )

        logger.msg("Face comparison complete", application_id=application_id, match=result.get("is_match"))
        return {"application_id": application_id, "status": "completed", "result": result}

    except Exception as exc:
        logger.error("Face comparison failed", application_id=application_id, error=str(exc))
        raise self.retry(exc=exc) from exc


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_fraud_check(self, document_id: str, image_path: str, ocr_data: dict | None = None):
    """Run fraud detection on a document."""
    try:
        from app.services.fraud_service import analyze_document

        logger.msg("Starting fraud check", document_id=document_id)

        result = _run_async(analyze_document(image_path, ocr_data=ocr_data))
        result_dict = result.to_dict()

        # Update document fraud score in DB
        _run_async(_update_document_fraud(document_id, result.overall_score, result_dict))

        logger.msg(
            "Fraud check complete",
            document_id=document_id,
            score=result.overall_score,
            flagged=result.is_flagged,
        )
        return {"document_id": document_id, "status": "completed", "fraud_result": result_dict}

    except Exception as exc:
        logger.error("Fraud check failed", document_id=document_id, error=str(exc))
        raise self.retry(exc=exc) from exc


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def run_scoring_pipeline(self, application_id: str, selfie_path: str):
    """After selfie upload, run full scoring: OCR, face extraction, comparisons, score."""
    try:
        from app.services.face_service import compare_faces, save_extracted_face
        from app.services.ocr_service import extract_text, get_raw_text, parse_document
        from app.services.scoring_service import compute_verification_score
        from app.utils.storage import get_storage

        logger.info("Starting scoring pipeline", application_id=application_id)
        _run_async(_update_application_status(application_id, "processing"))

        storage = get_storage()
        app_data = _run_async(_get_application_data(application_id))
        if not app_data:
            logger.error("Application not found", application_id=application_id)
            return {"status": "error"}

        documents = app_data.get("documents", [])
        passport_ocr = None
        id_ocr = None
        passport_face_path = None
        id_face_path = None
        face_comparisons = {}

        # Process each document: OCR + extract face
        for doc in documents:
            doc_abs_path = storage.get_absolute_path(doc["file_path"])

            # OCR
            ocr_results = extract_text(doc_abs_path)
            raw_text = get_raw_text(ocr_results)
            parsed = parse_document(raw_text, ocr_results, doc["doc_type"])
            _run_async(_update_document_ocr(doc["id"], parsed, raw_text))

            # Extract face from document
            face_out = doc_abs_path.rsplit(".", 1)[0] + "_face.jpg"
            face_found = save_extracted_face(doc_abs_path, face_out)
            if face_found:
                _run_async(_update_document_face_path(doc["id"], face_out))

            if doc["doc_type"] == "passport":
                passport_ocr = parsed
                if face_found:
                    passport_face_path = face_out
            elif doc["doc_type"] == "national_id":
                id_ocr = parsed
                if face_found:
                    id_face_path = face_out

            # Fraud check
            try:
                from app.services.fraud_service import analyze_document

                fraud_result = _run_async(analyze_document(doc_abs_path, ocr_data=parsed))
                _run_async(_update_document_fraud(doc["id"], fraud_result.overall_score, fraud_result.to_dict()))
            except Exception as e:
                logger.warning("Fraud check failed for doc", doc_id=doc["id"], error=str(e))

        # Face comparisons
        selfie_abs = storage.get_absolute_path(selfie_path) if "/" in selfie_path else selfie_path

        if passport_face_path:
            try:
                result = compare_faces(passport_face_path, selfie_abs)
                face_comparisons["passport_vs_selfie"] = result["similarity_score"]
            except Exception as e:
                logger.warning("Passport vs selfie failed", error=str(e))

        if id_face_path:
            try:
                result = compare_faces(id_face_path, selfie_abs)
                face_comparisons["id_vs_selfie"] = result["similarity_score"]
            except Exception as e:
                logger.warning("ID vs selfie failed", error=str(e))

        if passport_face_path and id_face_path:
            try:
                result = compare_faces(passport_face_path, id_face_path)
                face_comparisons["passport_vs_id"] = result["similarity_score"]
            except Exception as e:
                logger.warning("Passport vs ID face failed", error=str(e))

        # Compute final score
        score_result = compute_verification_score(passport_ocr, id_ocr, face_comparisons)

        # Save score to application
        _run_async(_update_application_score(application_id, score_result))
        _run_async(_update_application_status(application_id, "ready_for_review"))

        # Update face verification record
        best_face_score = face_comparisons.get("passport_vs_selfie", 0.0)
        is_match = best_face_score >= settings.face_similarity_threshold
        _run_async(
            _update_face_verification(
                application_id,
                best_face_score,
                is_match,
                "Facenet",
                passport_face_path,
            )
        )

        logger.info(
            "Scoring pipeline complete",
            application_id=application_id,
            total_score=score_result["total_score"],
            passed=score_result["passed"],
        )
        return {"application_id": application_id, "score": score_result}

    except Exception as exc:
        logger.error("Scoring pipeline failed", application_id=application_id, error=str(exc))
        _run_async(_update_application_status(application_id, "error"))
        raise self.retry(exc=exc) from exc


# --- DB helper functions (async) ---


async def _update_document_ocr(document_id: str, parsed_data: dict, raw_text: str):
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.document import Document

    async with async_session_factory() as session:
        result = await session.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
        doc = result.scalar_one_or_none()
        if doc:
            doc.ocr_data = parsed_data
            doc.ocr_raw_text = raw_text
            await session.commit()


async def _update_document_fraud(document_id: str, score: float, details: dict):
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.document import Document

    async with async_session_factory() as session:
        result = await session.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
        doc = result.scalar_one_or_none()
        if doc:
            doc.fraud_score = score
            doc.fraud_details = details
            await session.commit()


async def _update_face_verification(
    application_id: str,
    similarity_score: float,
    is_match: bool,
    model: str,
    doc_face_path: str | None,
):
    from datetime import datetime

    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.face_verification import FaceVerification

    async with async_session_factory() as session:
        result = await session.execute(
            select(FaceVerification)
            .where(FaceVerification.application_id == uuid.UUID(application_id))
            .order_by(FaceVerification.created_at.desc())
        )
        verification = result.scalar_one_or_none()
        if verification:
            verification.similarity_score = similarity_score
            verification.is_match = is_match
            verification.model_used = model
            verification.document_face_path = doc_face_path
            verification.verified_at = datetime.now(UTC)
            await session.commit()


async def _update_application_status(application_id: str, status: str):
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.idv_application import ApplicationStatus, IDVApplication

    async with async_session_factory() as session:
        result = await session.execute(select(IDVApplication).where(IDVApplication.id == uuid.UUID(application_id)))
        app = result.scalar_one_or_none()
        if app:
            app.status = ApplicationStatus(status)
            await session.commit()


async def _get_application_data(application_id: str) -> dict | None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import async_session_factory
    from app.models.idv_application import IDVApplication

    async with async_session_factory() as session:
        result = await session.execute(
            select(IDVApplication)
            .where(IDVApplication.id == uuid.UUID(application_id))
            .options(
                selectinload(IDVApplication.documents),
                selectinload(IDVApplication.face_verifications),
            )
        )
        app = result.scalar_one_or_none()
        if not app:
            return None

        selfie_path = None
        if app.face_verifications:
            selfie_path = app.face_verifications[-1].selfie_path

        return {
            "documents": [
                {"id": str(d.id), "file_path": d.file_path, "doc_type": d.doc_type.value} for d in app.documents
            ],
            "selfie_path": selfie_path,
        }


async def _update_document_face_path(document_id: str, face_path: str):
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.document import Document

    async with async_session_factory() as session:
        result = await session.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
        doc = result.scalar_one_or_none()
        if doc:
            doc.face_image_path = face_path
            await session.commit()


async def _update_application_score(application_id: str, score_result: dict):
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.idv_application import IDVApplication

    async with async_session_factory() as session:
        result = await session.execute(select(IDVApplication).where(IDVApplication.id == uuid.UUID(application_id)))
        app = result.scalar_one_or_none()
        if app:
            app.verification_score = score_result.get("total_score")
            app.score_details = score_result
            await session.commit()


# --- God-Level Pipeline Task ---


@celery_app.task(bind=True, max_retries=2, time_limit=300)
def run_god_pipeline(self, application_id: str):
    """Run the 10-stage God-Level verification pipeline."""
    try:
        logger.info("God pipeline task starting", application_id=application_id)
        result = _run_async(_execute_god_pipeline(application_id))
        logger.info(
            "God pipeline task complete",
            application_id=application_id,
            decision=result.get("decision"),
        )
        return result
    except Exception as exc:
        logger.error("God pipeline task failed", application_id=application_id, error=str(exc))
        raise self.retry(exc=exc) from exc


async def _execute_god_pipeline(application_id: str) -> dict:
    """Async wrapper that runs the pipeline with a fresh DB session."""
    from app.database import async_session_factory
    from app.services.pipeline import run_pipeline

    async with async_session_factory() as session:
        ctx = await run_pipeline(application_id, session)
        return {
            "application_id": application_id,
            "decision": ctx.final_decision,
            "weighted_total": ctx.weighted_total,
            "channel_scores": ctx.channel_scores,
            "flags": len(ctx.flags),
            "reason_codes": len(ctx.reason_codes),
            "stages_run": len(ctx.stage_results),
        }

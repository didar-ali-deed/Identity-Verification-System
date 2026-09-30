import asyncio
import uuid

import structlog
from celery.signals import worker_process_init

from app.tasks import celery_app

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

    async def run():
        from app.database import engine

        try:
            return await coro
        finally:
            # Dispose inside the owning loop, before asyncio.run closes it.
            await engine.dispose()

    return asyncio.run(run())


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
        return {"document_id": document_id, "status": "completed"}

    except Exception as exc:
        logger.error("OCR processing failed", document_id=document_id, error=str(exc))
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


# --- verification Pipeline Task ---


@celery_app.task(bind=True, max_retries=2, time_limit=300)
def run_god_pipeline(self, application_id: str):
    """Run verification; retain the registered task name for existing queued jobs."""
    try:
        logger.info("Verification task starting", application_id=application_id)
        result = _run_async(_execute_god_pipeline(application_id))
        logger.info(
            "Verification task complete",
            application_id=application_id,
            decision=result.get("decision"),
        )
        return result
    except Exception as exc:
        logger.error("Verification task failed", application_id=application_id, error=str(exc))
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

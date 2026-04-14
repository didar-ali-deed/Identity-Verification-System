"""Pipeline Orchestrator — runs all 10 stages in sequence.

Loads the application and documents, builds the PipelineContext,
and executes stages 0→9. If a stage hard-fails on stages 0-1,
the orchestrator skips to stage 7→8→9 (score synthesis is meaningless
when documents are fundamentally rejected).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.idv_application import ApplicationStatus, IDVApplication
from app.services.pipeline.stage_0_acceptance import run_stage_0
from app.services.pipeline.stage_1_liveness import run_stage_1
from app.services.pipeline.stage_2_extraction import run_stage_2
from app.services.pipeline.stage_3_normalization import run_stage_3
from app.services.pipeline.stage_4_internal_checks import run_stage_4
from app.services.pipeline.stage_5_similarity import run_stage_5
from app.services.pipeline.stage_6_scoring import run_stage_6
from app.services.pipeline.stage_7_hard_rules import run_stage_7
from app.services.pipeline.stage_8_decision import run_stage_8
from app.services.pipeline.stage_9_result import run_stage_9
from app.services.pipeline.types import PipelineContext
from app.utils.storage import LocalStorage

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def run_pipeline(application_id: str, db: AsyncSession) -> PipelineContext:
    """Execute the full 10-stage verification pipeline.

    Returns the completed PipelineContext with all results.
    """
    started_at = datetime.now(UTC)

    logger.info("Pipeline starting", application_id=application_id)

    # --- Load application + documents + face verifications ---
    result = await db.execute(
        select(IDVApplication)
        .options(
            selectinload(IDVApplication.documents),
            selectinload(IDVApplication.face_verifications),
        )
        .where(IDVApplication.id == application_id)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise ValueError(f"Application {application_id} not found")

    # Mark as processing
    application.status = ApplicationStatus.PROCESSING
    await db.flush()

    # --- Build context from documents ---
    ctx = _build_context(application)

    # --- Run pipeline stages ---
    try:
        # Stage 0: Document Acceptance
        stage_0 = await run_stage_0(ctx, db)
        if stage_0.hard_fail:
            logger.warning("Stage 0 hard fail — skipping to decision", application_id=application_id)
            await _skip_to_decision(ctx, db, started_at)
            return ctx

        # Stage 1: Liveness & Anti-Spoofing
        stage_1 = await run_stage_1(ctx)
        if stage_1.hard_fail:
            logger.warning("Stage 1 hard fail — skipping to decision", application_id=application_id)
            await _skip_to_decision(ctx, db, started_at)
            return ctx

        # Stage 2: Field Extraction
        await run_stage_2(ctx)

        # Stage 3: Normalization & Cross-Zone Consistency
        stage_3 = await run_stage_3(ctx)
        if stage_3.hard_fail:
            logger.warning("Stage 3 hard fail (expired doc) — skipping to decision", application_id=application_id)
            await _skip_to_decision(ctx, db, started_at)
            return ctx

        # Stage 4: Internal Checks (watchlist, duplicates, velocity)
        await run_stage_4(ctx, db)

        # Stage 5: 5-Channel Similarity
        await run_stage_5(ctx)

        # Stage 6: Weighted Score Synthesis
        await run_stage_6(ctx)

        # Stage 7: Hard-Rule Override
        await run_stage_7(ctx)

        # Stage 8: Decision Matrix
        await run_stage_8(ctx)

        # Stage 9: Persist result
        await run_stage_9(ctx, db, started_at)

        await db.commit()

    except Exception:
        logger.exception("Pipeline failed", application_id=application_id)
        await db.rollback()

        # Mark application as errored — must re-merge after rollback since the
        # session has expelled the instance.
        try:
            application.status = ApplicationStatus.ERROR
            db.add(application)
            await db.commit()
        except Exception:
            logger.exception("Failed to mark application as ERROR", application_id=application_id)
        raise

    logger.info(
        "Pipeline completed",
        application_id=application_id,
        decision=ctx.final_decision,
        weighted_total=ctx.weighted_total,
        stages_run=len(ctx.stage_results),
    )

    return ctx


async def _skip_to_decision(ctx: PipelineContext, db: AsyncSession, started_at: datetime) -> None:
    """When early hard-fail, skip to stages 7→8→9 for decision + persistence."""
    # Stages 7-8 still evaluate whatever flags exist
    await run_stage_7(ctx)
    await run_stage_8(ctx)
    await run_stage_9(ctx, db, started_at)
    await db.commit()


def _build_context(application: IDVApplication) -> PipelineContext:
    """Build PipelineContext from application and its documents."""
    ctx = PipelineContext(application_id=str(application.id))
    storage = LocalStorage()

    for doc in application.documents:
        doc_type = doc.doc_type.lower() if doc.doc_type else ""
        abs_path = storage.get_absolute_path(doc.file_path)

        if doc_type == "passport":
            ctx.passport_image_path = abs_path
            ctx.passport_doc_id = str(doc.id)
            # Pre-populate raw text from existing OCR if available
            if doc.ocr_data and isinstance(doc.ocr_data, dict):
                ctx.passport_raw_text = doc.ocr_data.get("raw_text", "")

        elif doc_type in ("national_id", "id_card"):
            ctx.id_image_path = abs_path
            ctx.id_doc_id = str(doc.id)
            if doc.ocr_data and isinstance(doc.ocr_data, dict):
                ctx.id_raw_text = doc.ocr_data.get("raw_text", "")

        elif doc_type == "selfie":
            ctx.selfie_image_path = abs_path

    # Selfie is stored in FaceVerification, not Document — use the latest one
    if application.face_verifications:
        latest_selfie = sorted(
            application.face_verifications,
            key=lambda fv: fv.created_at,
            reverse=True,
        )[0]
        ctx.selfie_image_path = storage.get_absolute_path(latest_selfie.selfie_path)

    return ctx

"""Stage 9 — Result Object & Audit Trail.

Persists the immutable PipelineResult, updates the IDV application status,
and stores per-document metadata (liveness scores, normalized data, etc.).
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from app.config import get_settings
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.face_verification import FaceVerification
from app.models.idv_application import ApplicationStatus, IDVApplication
from app.models.pipeline_result import PipelineResult
from app.services.pipeline.types import PipelineContext, StageResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Map pipeline decision to application status
DECISION_STATUS_MAP = {
    "APPROVED": ApplicationStatus.APPROVED,
    "REJECTED": ApplicationStatus.REJECTED,
    "MANUAL_REVIEW": ApplicationStatus.READY_FOR_REVIEW,
}


def _get_stage_dict(ctx: PipelineContext, stage_num: int) -> dict | None:
    """Extract a stage result dict by stage number."""
    for sr in ctx.stage_results:
        if sr.stage == stage_num:
            return sr.to_dict()
    return None


async def run_stage_9(
    ctx: PipelineContext,
    db: AsyncSession,
    started_at: datetime,
) -> StageResult:
    """Run Stage 9: Persist result and update application."""
    start = time.time()
    details = {}

    completed_at = datetime.now(UTC)

    # --- Build PipelineResult ---
    pipeline_result = PipelineResult(
        id=uuid.uuid4(),
        application_id=ctx.application_id,
        pipeline_version="2.0",
        stage_0_result=_get_stage_dict(ctx, 0),
        stage_1_result=_get_stage_dict(ctx, 1),
        stage_2_result=_get_stage_dict(ctx, 2),
        stage_3_result=_get_stage_dict(ctx, 3),
        stage_4_result=_get_stage_dict(ctx, 4),
        channel_a_score=ctx.channel_scores.get("A"),
        channel_b_score=ctx.channel_scores.get("B"),
        channel_c_score=ctx.channel_scores.get("C"),
        channel_d_score=ctx.channel_scores.get("D"),
        channel_e_score=ctx.channel_scores.get("E"),
        weighted_total=ctx.weighted_total,
        hard_rules_result=_get_stage_dict(ctx, 7),
        decision_override=ctx.decision_override,
        final_decision=ctx.final_decision,
        reason_codes=ctx.reason_codes,
        flags=ctx.flags,
        started_at=started_at,
        completed_at=completed_at,
    )

    # A retry must never overwrite a final decision or a reviewer's work.
    existing = await db.execute(select(PipelineResult).where(PipelineResult.application_id == ctx.application_id))
    old = existing.scalar_one_or_none()
    if old:
        raise RuntimeError("A final pipeline result already exists")

    db.add(pipeline_result)
    details["pipeline_result_id"] = str(pipeline_result.id)

    # --- Update IDV application ---
    app_result = await db.execute(select(IDVApplication).where(IDVApplication.id == ctx.application_id))
    application = app_result.scalar_one_or_none()

    if application:
        application.pipeline_version = "2.0"
        application.pipeline_decision = ctx.final_decision

        new_status = DECISION_STATUS_MAP.get(ctx.final_decision)
        if new_status:
            application.status = new_status

        # Store weighted total as verification_score for backward compat
        application.verification_score = ctx.weighted_total * 100  # 0-100 scale
        application.score_details = {
            "pipeline_version": "2.0",
            "channel_scores": ctx.channel_scores,
            "weighted_total": ctx.weighted_total,
            "decision": ctx.final_decision,
            "override": ctx.decision_override,
            "flag_count": len(ctx.flags),
            "reason_code_count": len(ctx.reason_codes),
        }

        details["application_status"] = new_status.value if new_status else None
        details["verification_score"] = application.verification_score

    selfie = (
        await db.execute(
            select(FaceVerification)
            .where(FaceVerification.application_id == ctx.application_id)
            .order_by(FaceVerification.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if selfie:
        selfie.similarity_score = ctx.channel_scores.get("A")
        selfie.is_match = (ctx.channel_scores.get("A") or 0.0) >= get_settings().face_similarity_threshold
        selfie.verified_at = completed_at
    db.add(
        AuditLog(
            application_id=ctx.application_id,
            action="pipeline_completed",
            performed_by=None,
            details={
                "decision": ctx.final_decision,
                "override": ctx.decision_override,
                "pipeline_version": "2.0",
                "reason_codes": ctx.reason_codes,
            },
        )
    )

    # --- Update document records ---
    for doc_id, label, normalized, liveness_stage_key in [
        (ctx.passport_doc_id, "passport", ctx.normalized_passport, "passport_liveness"),
        (ctx.id_doc_id, "national_id", ctx.normalized_id, "national_id_liveness"),
    ]:
        if not doc_id:
            continue

        doc_result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = doc_result.scalar_one_or_none()
        if not doc:
            continue

        # Document class
        if label == "passport":
            doc.document_class = ctx.passport_doc_class
            doc.issuing_country = ctx.passport_country
        else:
            doc.document_class = ctx.id_doc_class
            doc.issuing_country = ctx.id_country

        # Normalized data
        if normalized:
            doc.normalized_data = normalized

        # Liveness score from stage 1
        stage_1 = _get_stage_dict(ctx, 1)
        if stage_1 and stage_1.get("details"):
            liveness_data = stage_1["details"].get(liveness_stage_key)
            if liveness_data:
                doc.liveness_score = liveness_data.get("score")
                doc.liveness_details = liveness_data

    await db.flush()

    duration = (time.time() - start) * 1000
    result = StageResult(
        stage=9,
        name="Result Object & Audit Trail",
        passed=True,
        details=details,
        duration_ms=duration,
    )
    ctx.stage_results.append(result)
    pipeline_result.stage_results = [stage.to_dict() for stage in ctx.stage_results]
    await db.flush()

    logger.info(
        "Pipeline completed",
        application_id=ctx.application_id,
        decision=ctx.final_decision,
        weighted_total=ctx.weighted_total,
        flags=len(ctx.flags),
        duration_ms=round(duration, 2),
    )

    return result

"""Stage 8 — Decision Matrix.

Combines the weighted score with any hard-rule overrides to produce
the final pipeline decision: APPROVED, MANUAL_REVIEW, or REJECTED.
"""

from __future__ import annotations

import time

import structlog

from app.config import get_settings
from app.services.pipeline.types import PipelineContext, StageResult

settings = get_settings()
logger = structlog.get_logger()


def compute_decision(
    weighted_total: float,
    decision_override: str | None,
) -> str:
    """Determine final decision from score + override.

    Priority: hard_reject → REJECTED, manual_review → MANUAL_REVIEW,
    then score thresholds.
    """
    if decision_override == "hard_reject":
        return "REJECTED"

    if decision_override == "manual_review":
        return "MANUAL_REVIEW"

    if weighted_total >= settings.pipeline_pass_threshold:
        return "APPROVED"

    if weighted_total >= settings.pipeline_review_threshold:
        return "MANUAL_REVIEW"

    return "REJECTED"


async def run_stage_8(ctx: PipelineContext) -> StageResult:
    """Run Stage 8: Decision Matrix."""
    start = time.time()

    decision = compute_decision(ctx.weighted_total, ctx.decision_override)
    ctx.final_decision = decision

    details = {
        "weighted_total": ctx.weighted_total,
        "decision_override": ctx.decision_override,
        "pass_threshold": settings.pipeline_pass_threshold,
        "review_threshold": settings.pipeline_review_threshold,
        "final_decision": decision,
        "decision_basis": (
            f"Override: {ctx.decision_override}"
            if ctx.decision_override
            else (
                f"Score {ctx.weighted_total:.4f} vs thresholds "
                f"(pass={settings.pipeline_pass_threshold}, review={settings.pipeline_review_threshold})"
            )
        ),
    }

    duration = (time.time() - start) * 1000
    result = StageResult(
        stage=8,
        name="Decision Matrix",
        passed=decision != "REJECTED",
        details=details,
        duration_ms=duration,
    )
    ctx.stage_results.append(result)
    return result

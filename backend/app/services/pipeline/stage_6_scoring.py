"""Stage 6 — Weighted Score Synthesis.

Combines 5 channel scores into a single weighted total using fixed weights.
"""

from __future__ import annotations

import time

import structlog

from app.services.pipeline.types import PipelineContext, StageResult

logger = structlog.get_logger()

# Channel weights (must sum to 1.0)
CHANNEL_WEIGHTS = {
    "A": 0.40,  # Biometric face similarity
    "B": 0.25,  # ID number match
    "C": 0.15,  # Full name similarity
    "D": 0.10,  # Father's name similarity
    "E": 0.10,  # DOB match
}


def compute_weighted_score(channel_scores: dict[str, float]) -> float:
    """Compute weighted total from channel scores."""
    total = 0.0
    for channel, weight in CHANNEL_WEIGHTS.items():
        score = channel_scores.get(channel, 0.0)
        total += score * weight
    return round(total, 4)


async def run_stage_6(ctx: PipelineContext) -> StageResult:
    """Run Stage 6: Weighted Score Synthesis."""
    start = time.time()

    weighted_total = compute_weighted_score(ctx.channel_scores)
    ctx.weighted_total = weighted_total

    breakdown = {
        channel: {
            "score": ctx.channel_scores.get(channel, 0.0),
            "weight": weight,
            "contribution": round(ctx.channel_scores.get(channel, 0.0) * weight, 4),
        }
        for channel, weight in CHANNEL_WEIGHTS.items()
    }

    details = {
        "weighted_total": weighted_total,
        "channel_weights": CHANNEL_WEIGHTS,
        "breakdown": breakdown,
    }

    duration = (time.time() - start) * 1000
    result = StageResult(
        stage=6,
        name="Weighted Score Synthesis",
        passed=True,
        details=details,
        duration_ms=duration,
    )
    ctx.stage_results.append(result)
    return result

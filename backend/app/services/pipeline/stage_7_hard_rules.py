"""Stage 7 — Hard-Rule Override Layer.

Applies deterministic rules that override the weighted score. Each rule
evaluates accumulated flags/reason_codes and emits either a hard_reject
or manual_review override. Worst outcome wins.
"""

from __future__ import annotations

import time

import structlog

from app.services.pipeline.types import PipelineContext, StageResult

logger = structlog.get_logger()

# Rule definitions: (rule_name, flag_types_to_match, override_action)
# override_action: "hard_reject" or "manual_review"
HARD_RULES: list[tuple[str, list[str], str]] = [
    ("id_mismatch", ["id_mismatch"], "hard_reject"),
    ("document_expired", ["document_expired"], "hard_reject"),
    ("doc_liveness_fail", ["doc_liveness_fail"], "hard_reject"),
    ("selfie_liveness_fail", ["selfie_liveness_fail"], "hard_reject"),
    ("sanctioned_country", ["sanctioned_country"], "hard_reject"),
    ("viz_mrz_mismatch", ["viz_mrz_mismatch"], "manual_review"),
    ("ocr_confidence_fail", ["low_ocr_confidence"], "manual_review"),
    ("watchlist_hit", ["watchlist_hit"], "manual_review"),
    ("structural_id_invalid", ["structural_id_invalid"], "manual_review"),
    ("duplicate_active", ["duplicate_active"], "manual_review"),
    ("velocity_exceeded", ["velocity_exceeded"], "manual_review"),
]

# Priority: hard_reject > manual_review > None
OVERRIDE_PRIORITY = {"hard_reject": 2, "manual_review": 1}


def evaluate_hard_rules(ctx: PipelineContext) -> dict:
    """Evaluate all hard rules against accumulated flags.

    Returns dict with triggered rules, worst override, and per-rule details.
    """
    flag_types = {f["flag_type"] for f in ctx.flags}
    triggered = []
    worst_override = None

    for rule_name, match_flags, action in HARD_RULES:
        matched = [f for f in match_flags if f in flag_types]
        if matched:
            triggered.append(
                {
                    "rule": rule_name,
                    "matched_flags": matched,
                    "action": action,
                }
            )

            current_priority = OVERRIDE_PRIORITY.get(action, 0)
            worst_priority = OVERRIDE_PRIORITY.get(worst_override, 0)
            if current_priority > worst_priority:
                worst_override = action

    return {
        "triggered_rules": triggered,
        "override": worst_override,
        "rule_count": len(triggered),
        "detail": (
            f"{len(triggered)} rule(s) triggered → {worst_override}" if triggered else "No hard rules triggered"
        ),
    }


async def run_stage_7(ctx: PipelineContext) -> StageResult:
    """Run Stage 7: Hard-Rule Override Layer."""
    start = time.time()

    rules_result = evaluate_hard_rules(ctx)
    ctx.decision_override = rules_result["override"]

    details = {
        "triggered_rules": rules_result["triggered_rules"],
        "override": rules_result["override"],
        "total_flags_evaluated": len(ctx.flags),
    }

    # If hard_reject, add reason codes for the triggered rules
    flags = []
    reason_codes = []

    if rules_result["override"] == "hard_reject":
        for rule in rules_result["triggered_rules"]:
            if rule["action"] == "hard_reject":
                reason_codes.append(
                    {
                        "code": f"HARD_RULE_{rule['rule'].upper()}",
                        "stage": 7,
                        "severity": "critical",
                        "message": f"Hard rule triggered: {rule['rule']}",
                    }
                )

    duration = (time.time() - start) * 1000
    result = StageResult(
        stage=7,
        name="Hard-Rule Override Layer",
        passed=rules_result["override"] != "hard_reject",
        hard_fail=rules_result["override"] == "hard_reject",
        details=details,
        flags=flags,
        reason_codes=reason_codes,
        duration_ms=duration,
    )
    ctx.stage_results.append(result)
    ctx.flags.extend(flags)
    ctx.reason_codes.extend(reason_codes)
    return result

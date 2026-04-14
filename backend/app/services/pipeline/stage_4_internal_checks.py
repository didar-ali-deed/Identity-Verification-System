"""Stage 4 — Fraud & Watchlist Screening.

Checks internal watchlist, duplicate active submissions, velocity limits,
and self-reported vs extracted data consistency.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, select

from app.config import get_settings
from app.models.idv_application import ApplicationStatus, IDVApplication
from app.models.watchlist_entry import WatchlistEntry
from app.services.pipeline.types import PipelineContext, StageResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()
logger = structlog.get_logger()


async def check_watchlist(
    id_number: str | None,
    full_name: str | None,
    db: AsyncSession,
) -> dict:
    """Query watchlist_entries by ID number and fuzzy name match."""
    hits = []

    if not id_number and not full_name:
        return {"hit": False, "matches": [], "detail": "No identifiers to check"}

    # Exact ID number match
    if id_number:
        result = await db.execute(
            select(WatchlistEntry).where(
                WatchlistEntry.id_number == id_number,
                WatchlistEntry.is_active.is_(True),
            )
        )
        for entry in result.scalars().all():
            hits.append(
                {
                    "match_type": "id_number_exact",
                    "id_number": entry.id_number,
                    "full_name": entry.full_name,
                    "reason": entry.reason,
                    "source": entry.source,
                }
            )

    # Name-based check (contains match — simple fuzzy)
    if full_name and not hits:
        name_upper = full_name.upper().strip()
        name_tokens = name_upper.split()

        if len(name_tokens) >= 2:
            result = await db.execute(
                select(WatchlistEntry).where(
                    WatchlistEntry.is_active.is_(True),
                    WatchlistEntry.full_name.isnot(None),
                )
            )
            for entry in result.scalars().all():
                if not entry.full_name:
                    continue
                entry_tokens = set(entry.full_name.upper().split())
                overlap = set(name_tokens) & entry_tokens
                # Require at least 2 tokens to match to avoid false positives
                if len(overlap) >= 2:
                    hits.append(
                        {
                            "match_type": "name_fuzzy",
                            "id_number": entry.id_number,
                            "full_name": entry.full_name,
                            "reason": entry.reason,
                            "source": entry.source,
                            "matching_tokens": list(overlap),
                        }
                    )

    return {
        "hit": len(hits) > 0,
        "matches": hits,
        "detail": f"{len(hits)} watchlist hit(s)" if hits else "No watchlist hits",
    }


async def check_duplicate_active(
    id_number: str | None,
    current_application_id: str,
    db: AsyncSession,
) -> dict:
    """Check if same ID number has another active (non-rejected) application."""
    if not id_number:
        return {"duplicate": False, "detail": "No ID number to check"}

    from app.models.document import Document

    # Find documents with the same extracted ID number in other applications
    result = await db.execute(
        select(Document.application_id)
        .join(IDVApplication, IDVApplication.id == Document.application_id)
        .where(
            Document.ocr_data["national_id_number"].astext == id_number,
            IDVApplication.id != current_application_id,
            IDVApplication.status.in_(
                [
                    ApplicationStatus.PENDING,
                    ApplicationStatus.PROCESSING,
                    ApplicationStatus.READY_FOR_REVIEW,
                    ApplicationStatus.APPROVED,
                ]
            ),
        )
        .distinct()
    )
    dup_app_ids = [str(row[0]) for row in result.all()]

    if dup_app_ids:
        return {
            "duplicate": True,
            "matching_applications": dup_app_ids,
            "detail": f"ID {id_number} found in {len(dup_app_ids)} other active application(s)",
        }

    return {"duplicate": False, "detail": "No duplicate active applications"}


async def check_velocity(
    user_id: str,
    db: AsyncSession,
) -> dict:
    """Check submission velocity: how many apps in the configured window."""
    window_start = datetime.now(UTC) - timedelta(hours=settings.velocity_window_hours)

    result = await db.execute(
        select(func.count(IDVApplication.id)).where(
            IDVApplication.user_id == user_id,
            IDVApplication.submitted_at >= window_start,
        )
    )
    count = result.scalar() or 0

    exceeded = count > settings.velocity_max_submissions

    return {
        "submission_count": count,
        "window_hours": settings.velocity_window_hours,
        "max_allowed": settings.velocity_max_submissions,
        "exceeded": exceeded,
        "detail": (
            f"{count} submissions in {settings.velocity_window_hours}h window (max {settings.velocity_max_submissions})"
        ),
    }


def check_form_consistency(
    form_data: dict | None,
    normalized_passport: dict | None,
    normalized_id: dict | None,
) -> dict:
    """Compare self-reported form data against extracted/normalized document data."""
    if not form_data:
        return {"score": 1.0, "checks": {}, "detail": "No form data to compare"}

    checks = {}
    mismatches = []

    # Fields to compare
    compare_fields = [
        ("full_name", "full_name"),
        ("date_of_birth", "dob"),
        ("nationality", "nationality"),
        ("id_number", "national_id_number"),
    ]

    for form_key, doc_key in compare_fields:
        form_val = form_data.get(form_key)
        if not form_val:
            continue

        # Check against both documents
        doc_val = None
        source = None
        if normalized_passport and normalized_passport.get(doc_key):
            doc_val = normalized_passport[doc_key]
            source = "passport"
        elif normalized_id and normalized_id.get(doc_key):
            doc_val = normalized_id[doc_key]
            source = "national_id"

        if not doc_val:
            continue

        # Normalize both for comparison
        form_norm = str(form_val).upper().strip()
        doc_norm = str(doc_val).upper().strip()

        match = form_norm == doc_norm
        checks[form_key] = {
            "match": match,
            "form_value": form_norm,
            "doc_value": doc_norm,
            "source": source,
        }

        if not match:
            mismatches.append(form_key)

    total = len(checks)
    matched = sum(1 for c in checks.values() if c["match"])
    score = matched / max(total, 1)

    return {
        "score": round(score, 4),
        "checks": checks,
        "mismatches": mismatches,
        "detail": f"{matched}/{total} form fields match extracted data",
    }


async def run_stage_4(ctx: PipelineContext, db: AsyncSession) -> StageResult:
    """Run Stage 4: Fraud & Watchlist Screening."""
    start = time.time()
    details = {}
    flags = []
    reason_codes = []
    passed = True

    # Get identity fields from normalized data
    id_number = None
    full_name = None

    if ctx.normalized_passport:
        id_number = ctx.normalized_passport.get("national_id_number")
        full_name = ctx.normalized_passport.get("full_name")
    if not id_number and ctx.normalized_id:
        id_number = ctx.normalized_id.get("national_id_number")
    if not full_name and ctx.normalized_id:
        full_name = ctx.normalized_id.get("full_name")

    # --- Watchlist check ---
    watchlist_result = await check_watchlist(id_number, full_name, db)
    details["watchlist"] = watchlist_result

    if watchlist_result["hit"]:
        flags.append(
            {
                "flag_type": "watchlist_hit",
                "detail": watchlist_result["detail"],
            }
        )
        reason_codes.append(
            {
                "code": "WATCHLIST_HIT",
                "stage": 4,
                "severity": "critical",
                "message": f"Watchlist match: {watchlist_result['detail']}",
            }
        )

    # --- Duplicate active check ---
    duplicate_result = await check_duplicate_active(id_number, ctx.application_id, db)
    details["duplicate_check"] = duplicate_result

    if duplicate_result["duplicate"]:
        flags.append(
            {
                "flag_type": "duplicate_active",
                "detail": duplicate_result["detail"],
            }
        )
        reason_codes.append(
            {
                "code": "DUPLICATE_ACTIVE",
                "stage": 4,
                "severity": "warning",
                "message": duplicate_result["detail"],
            }
        )

    # --- Velocity check ---
    # Extract user_id from the application
    app_result = await db.execute(select(IDVApplication.user_id).where(IDVApplication.id == ctx.application_id))
    user_row = app_result.first()
    if user_row:
        velocity_result = await check_velocity(str(user_row[0]), db)
        details["velocity"] = velocity_result

        if velocity_result["exceeded"]:
            flags.append(
                {
                    "flag_type": "velocity_exceeded",
                    "detail": velocity_result["detail"],
                }
            )
            reason_codes.append(
                {
                    "code": "VELOCITY_EXCEEDED",
                    "stage": 4,
                    "severity": "warning",
                    "message": velocity_result["detail"],
                }
            )

    # --- Form consistency check ---
    form_result = check_form_consistency(ctx.form_data, ctx.normalized_passport, ctx.normalized_id)
    details["form_consistency"] = form_result

    if form_result.get("mismatches"):
        flags.append(
            {
                "flag_type": "form_data_mismatch",
                "detail": f"Form/document mismatch on: {', '.join(form_result['mismatches'])}",
            }
        )
        reason_codes.append(
            {
                "code": "FORM_DATA_MISMATCH",
                "stage": 4,
                "severity": "warning",
                "message": f"Self-reported data does not match documents: {form_result['mismatches']}",
            }
        )

    duration = (time.time() - start) * 1000
    result = StageResult(
        stage=4,
        name="Fraud & Watchlist Screening",
        passed=passed,
        details=details,
        flags=flags,
        reason_codes=reason_codes,
        duration_ms=duration,
    )
    ctx.stage_results.append(result)
    ctx.flags.extend(flags)
    ctx.reason_codes.extend(reason_codes)
    return result

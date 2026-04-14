"""Stage 5 — 5-Channel Similarity Extraction.

Computes independent similarity scores across five channels:
  A: Biometric face similarity (selfie vs document faces)
  B: Identity number match (binary)
  C: Full name similarity (Jaccard + Levenshtein)
  D: Father's name similarity (edit distance)
  E: Date-of-birth match (binary with transposition detection)
"""

from __future__ import annotations

import time

import structlog

from app.services.pipeline.stage_3_normalization import (
    normalize_father_name,
    normalize_id_number,
    normalize_name,
)
from app.services.pipeline.types import PipelineContext, StageResult

logger = structlog.get_logger()


def compute_channel_a(ctx: PipelineContext) -> dict:
    """Channel A: Biometric face similarity.

    min(selfie-vs-passport, selfie-vs-ID) face similarity via DeepFace.
    """
    if not ctx.selfie_image_path:
        return {"score": 0.0, "detail": "No selfie available"}

    from app.services.face_service import FaceServiceError, compare_faces

    scores = []
    comparisons = {}

    for label, face_path in [
        ("passport", ctx.passport_face_path),
        ("national_id", ctx.id_face_path),
    ]:
        if not face_path:
            continue

        try:
            result = compare_faces(ctx.selfie_image_path, face_path)
            sim = result.get("similarity_score", 0.0)
            scores.append(sim)
            comparisons[f"selfie_vs_{label}"] = {
                "similarity": sim,
                "distance": result.get("distance"),
                "verified": result.get("verified"),
            }
        except FaceServiceError as e:
            comparisons[f"selfie_vs_{label}"] = {"error": str(e.detail)}

    if not scores:
        return {"score": 0.0, "comparisons": comparisons, "detail": "No face comparisons succeeded"}

    # Use the minimum score (weakest match is the bottleneck)
    final_score = min(scores)

    return {
        "score": round(final_score, 4),
        "comparisons": comparisons,
        "detail": f"Biometric score {final_score:.4f} (min of {len(scores)} comparisons)",
    }


def compute_channel_b(ctx: PipelineContext) -> dict:
    """Channel B: Identity number match (binary 1.0 or 0.0).

    Compares national ID number across passport and national ID documents.
    """
    passport_id = None
    id_card_id = None

    if ctx.normalized_passport:
        passport_id = ctx.normalized_passport.get("national_id_number")
    if ctx.normalized_id:
        id_card_id = ctx.normalized_id.get("national_id_number")

    if not passport_id and not id_card_id:
        return {"score": 0.0, "detail": "No ID numbers extracted from either document"}

    if not passport_id or not id_card_id:
        # Only one document has ID number — can't cross-compare
        return {
            "score": 1.0,
            "passport_id": passport_id,
            "id_card_id": id_card_id,
            "detail": "Single-document ID — no cross-compare needed",
        }

    match = normalize_id_number(passport_id) == normalize_id_number(id_card_id)
    score = 1.0 if match else 0.0

    return {
        "score": score,
        "passport_id": passport_id,
        "id_card_id": id_card_id,
        "match": match,
        "detail": f"ID numbers {'match' if match else 'MISMATCH'}",
    }


def compute_channel_c(ctx: PipelineContext) -> dict:
    """Channel C: Full name similarity.

    Order-invariant token Jaccard + normalized Levenshtein, averaged.
    """
    passport_name = None
    id_name = None

    if ctx.normalized_passport:
        passport_name = ctx.normalized_passport.get("full_name")
    if ctx.normalized_id:
        id_name = ctx.normalized_id.get("full_name")

    if not passport_name and not id_name:
        return {"score": 0.0, "detail": "No names extracted"}

    if not passport_name or not id_name:
        return {
            "score": 1.0,
            "detail": "Single-document name — no cross-compare needed",
        }

    name_a = normalize_name(passport_name) or ""
    name_b = normalize_name(id_name) or ""

    if not name_a or not name_b:
        return {"score": 0.0, "detail": "Names normalize to empty"}

    # Token Jaccard similarity (order-invariant)
    tokens_a = set(name_a.split())
    tokens_b = set(name_b.split())
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union) if union else 0.0

    # Normalized Levenshtein distance
    lev_dist = _levenshtein(name_a, name_b)
    max_len = max(len(name_a), len(name_b))
    lev_sim = 1.0 - (lev_dist / max_len) if max_len > 0 else 1.0

    # Average both metrics
    score = 0.5 * jaccard + 0.5 * lev_sim

    return {
        "score": round(score, 4),
        "passport_name": name_a,
        "id_name": name_b,
        "jaccard": round(jaccard, 4),
        "levenshtein_similarity": round(lev_sim, 4),
        "detail": f"Name similarity {score:.4f} (Jaccard={jaccard:.3f}, Lev={lev_sim:.3f})",
    }


def compute_channel_d(ctx: PipelineContext) -> dict:
    """Channel D: Father's name similarity (normalized edit distance)."""
    passport_father = None
    id_father = None

    if ctx.normalized_passport:
        passport_father = ctx.normalized_passport.get("father_name")
    if ctx.normalized_id:
        id_father = ctx.normalized_id.get("father_name")

    if not passport_father and not id_father:
        # Father's name not available in either — neutral score
        return {"score": 1.0, "detail": "Father name not available — neutral"}

    if not passport_father or not id_father:
        return {
            "score": 1.0,
            "detail": "Single-document father name — no cross-compare needed",
        }

    name_a = normalize_father_name(passport_father) or ""
    name_b = normalize_father_name(id_father) or ""

    if not name_a or not name_b:
        return {"score": 1.0, "detail": "Father names normalize to empty — neutral"}

    lev_dist = _levenshtein(name_a, name_b)
    max_len = max(len(name_a), len(name_b))
    score = 1.0 - (lev_dist / max_len) if max_len > 0 else 1.0

    return {
        "score": round(score, 4),
        "passport_father": name_a,
        "id_father": name_b,
        "edit_distance": lev_dist,
        "detail": f"Father name similarity {score:.4f} (edit dist={lev_dist})",
    }


def compute_channel_e(ctx: PipelineContext) -> dict:
    """Channel E: Date-of-birth match (binary with transposition detection).

    Exact match = 1.0, single-digit transposition = 0.0 with flag, mismatch = 0.0.
    """
    passport_dob = None
    id_dob = None

    if ctx.normalized_passport:
        passport_dob = ctx.normalized_passport.get("dob")
    if ctx.normalized_id:
        id_dob = ctx.normalized_id.get("dob")

    if not passport_dob and not id_dob:
        return {"score": 0.0, "detail": "No DOB extracted"}

    if not passport_dob or not id_dob:
        return {
            "score": 1.0,
            "detail": "Single-document DOB — no cross-compare needed",
        }

    if passport_dob == id_dob:
        return {
            "score": 1.0,
            "passport_dob": passport_dob,
            "id_dob": id_dob,
            "detail": "DOB exact match",
        }

    # Check for single-digit transposition
    transposition = _is_single_transposition(passport_dob, id_dob)

    return {
        "score": 0.0,
        "passport_dob": passport_dob,
        "id_dob": id_dob,
        "transposition_detected": transposition,
        "detail": (
            "DOB mismatch (single-digit transposition detected — possible OCR error)"
            if transposition
            else "DOB mismatch"
        ),
    }


async def run_stage_5(ctx: PipelineContext) -> StageResult:
    """Run Stage 5: 5-Channel Similarity Extraction."""
    start = time.time()
    details = {}
    flags = []
    reason_codes = []

    # Compute all channels
    channel_a = compute_channel_a(ctx)
    channel_b = compute_channel_b(ctx)
    channel_c = compute_channel_c(ctx)
    channel_d = compute_channel_d(ctx)
    channel_e = compute_channel_e(ctx)

    ctx.channel_scores = {
        "A": channel_a["score"],
        "B": channel_b["score"],
        "C": channel_c["score"],
        "D": channel_d["score"],
        "E": channel_e["score"],
    }

    details["channel_a_biometric"] = channel_a
    details["channel_b_id_number"] = channel_b
    details["channel_c_name"] = channel_c
    details["channel_d_father_name"] = channel_d
    details["channel_e_dob"] = channel_e
    details["scores_summary"] = ctx.channel_scores

    # Flag critical mismatches
    if channel_b["score"] == 0.0 and channel_b.get("match") is False:
        flags.append(
            {
                "flag_type": "id_mismatch",
                "detail": f"ID numbers do not match: {channel_b.get('passport_id')} vs {channel_b.get('id_card_id')}",
            }
        )
        reason_codes.append(
            {
                "code": "ID_NUMBER_MISMATCH",
                "stage": 5,
                "severity": "critical",
                "message": "Identity numbers across documents do not match",
            }
        )

    if channel_e.get("transposition_detected"):
        flags.append(
            {
                "flag_type": "dob_transposition",
                "detail": "DOB differs by a single-digit transposition — possible OCR error",
            }
        )

    duration = (time.time() - start) * 1000
    result = StageResult(
        stage=5,
        name="5-Channel Similarity Extraction",
        passed=True,
        details=details,
        flags=flags,
        reason_codes=reason_codes,
        duration_ms=duration,
    )
    ctx.stage_results.append(result)
    ctx.flags.extend(flags)
    ctx.reason_codes.extend(reason_codes)
    return result


# --- Private helpers ---


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)

    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))

    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def _is_single_transposition(a: str, b: str) -> bool:
    """Check if two strings differ by exactly one adjacent-character transposition."""
    if len(a) != len(b):
        return False

    diffs = [(i, a[i], b[i]) for i in range(len(a)) if a[i] != b[i]]
    if len(diffs) != 2:
        return False

    i1, i2 = diffs[0][0], diffs[1][0]
    if i2 - i1 != 1:
        return False

    # Check that swapping fixes it
    return a[i1] == b[i2] and a[i2] == b[i1]

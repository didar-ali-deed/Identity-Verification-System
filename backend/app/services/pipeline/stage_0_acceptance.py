"""Stage 0 — Document Acceptance & National Validity Gate.

Before any extraction begins, every submitted document passes an internal
acceptance check. Fail here and nothing else runs.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

import cv2
import structlog
from sqlalchemy import select

from app.models.approved_country import ApprovedCountry
from app.models.document_class_rule import DocumentClassRule
from app.services.pipeline.types import PipelineContext, StageResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Expected aspect ratios (width/height) for document types
DOC_ASPECT_RATIOS = {
    "TD1": (1.50, 1.68),  # ID card ~85.6mm x 54mm ≈ 1.586
    "TD2": (1.35, 1.55),  # ~105mm x 74mm ≈ 1.42
    "TD3": (1.30, 1.55),  # Passport page ~125mm x 88mm ≈ 1.42
}


def classify_document(raw_text: str, image_path: str | None = None) -> str | None:
    """Classify document as TD1, TD2, or TD3 based on MRZ characteristics.

    TD3: 2 MRZ lines of ~44 chars (passport)
    TD2: 2 MRZ lines of ~36 chars
    TD1: 3 MRZ lines of ~30 chars (ID card)
    """
    clean_text = raw_text.replace(" ", "").upper()

    # Look for MRZ-like lines
    mrz_lines = []
    for segment in re.split(r"[\n\r]+", clean_text):
        cleaned = re.sub(r"[^A-Z0-9<]", "", segment)
        if len(cleaned) >= 25 and "<" in cleaned:
            mrz_lines.append(cleaned)

    # Also try pattern matching on full text
    if len(mrz_lines) < 2:
        pattern_44 = re.findall(r"[A-Z0-9<]{40,48}", clean_text)
        pattern_30 = re.findall(r"[A-Z0-9<]{26,34}", clean_text)
        pattern_36 = re.findall(r"[A-Z0-9<]{33,40}", clean_text)

        if len(pattern_44) >= 2:
            return "TD3"
        if len(pattern_30) >= 3:
            return "TD1"
        if len(pattern_36) >= 2:
            return "TD2"

    # Classify by line count and lengths
    if len(mrz_lines) >= 3:
        avg_len = sum(len(ln) for ln in mrz_lines[:3]) / 3
        if avg_len <= 34:
            return "TD1"

    if len(mrz_lines) >= 2:
        avg_len = sum(len(ln) for ln in mrz_lines[:2]) / 2
        if avg_len >= 40:
            return "TD3"
        if avg_len >= 33:
            return "TD2"

    # Fallback: check aspect ratio if image available
    if image_path:
        try:
            img = cv2.imread(image_path)
            if img is not None:
                h, w = img.shape[:2]
                aspect = w / max(h, 1)
                if aspect > 1.55:
                    return "TD1"  # wide card format
                if aspect < 1.0:
                    return "TD3"  # tall passport page
        except Exception:  # noqa: S110
            pass

    return None


async def validate_issuing_country(country_code: str, db: AsyncSession) -> dict:
    """Check country_code against approved_countries table."""
    if not country_code or len(country_code) != 3:
        return {
            "valid": False,
            "status": "unknown",
            "requires_edd": False,
            "detail": f"Invalid country code: {country_code}",
        }

    result = await db.execute(select(ApprovedCountry).where(ApprovedCountry.country_code == country_code.upper()))
    country = result.scalar_one_or_none()

    if not country:
        return {
            "valid": False,
            "status": "not_registered",
            "requires_edd": False,
            "detail": f"Country {country_code} not in approved registry",
        }

    if country.status == "sanctioned":
        return {
            "valid": False,
            "status": "sanctioned",
            "requires_edd": False,
            "detail": f"Country {country_code} is sanctioned — hard reject",
        }

    return {
        "valid": True,
        "status": country.status,
        "requires_edd": country.requires_edd,
        "detail": f"Country {country_code} ({country.country_name}) is {country.status}",
    }


async def check_document_class_eligibility(
    country_code: str,
    doc_class: str,
    application_type: str,
    db: AsyncSession,
) -> dict:
    """Check if a document class is allowed for this country + application type."""
    result = await db.execute(
        select(DocumentClassRule).where(
            DocumentClassRule.country_code == country_code.upper(),
            DocumentClassRule.document_class == doc_class,
            DocumentClassRule.application_type == application_type,
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        # No rule = allowed by default
        return {"eligible": True, "detail": "No restriction found — allowed by default"}

    if not rule.is_allowed:
        return {
            "eligible": False,
            "detail": f"{doc_class} not allowed for {application_type} from {country_code}",
        }

    return {
        "eligible": True,
        "is_required": rule.is_required,
        "detail": f"{doc_class} is allowed for {application_type}",
    }


def check_structural_plausibility(image_path: str, doc_class: str | None) -> dict:
    """Verify document layout matches expected template dimensions."""
    try:
        img = cv2.imread(image_path)
        if img is None:
            return {"plausible": False, "detail": "Cannot read image"}

        h, w = img.shape[:2]
        aspect = w / max(h, 1)

        if doc_class and doc_class in DOC_ASPECT_RATIOS:
            min_ratio, max_ratio = DOC_ASPECT_RATIOS[doc_class]
            if min_ratio <= aspect <= max_ratio:
                return {
                    "plausible": True,
                    "aspect_ratio": round(aspect, 3),
                    "expected_range": DOC_ASPECT_RATIOS[doc_class],
                    "detail": f"Aspect ratio {aspect:.3f} within expected range for {doc_class}",
                }
            return {
                "plausible": False,
                "aspect_ratio": round(aspect, 3),
                "expected_range": DOC_ASPECT_RATIOS[doc_class],
                "detail": f"Aspect ratio {aspect:.3f} outside expected {min_ratio}-{max_ratio} for {doc_class}",
            }

        # Unknown class — just check basic image sanity
        return {
            "plausible": True,
            "aspect_ratio": round(aspect, 3),
            "detail": "No class-specific template to validate against",
        }

    except Exception as e:
        return {"plausible": False, "detail": f"Structural check failed: {e}"}


async def run_stage_0(ctx: PipelineContext, db: AsyncSession) -> StageResult:
    """Run Stage 0: Document Acceptance & National Validity Gate."""
    start = time.time()
    details = {}
    flags = []
    reason_codes = []
    passed = True
    hard_fail = False

    # Classify passport
    if ctx.passport_image_path and ctx.passport_raw_text:
        cls = classify_document(ctx.passport_raw_text, ctx.passport_image_path)
        ctx.passport_doc_class = cls or "TD3"  # default passport to TD3
        details["passport_class"] = ctx.passport_doc_class

        if cls is None:
            flags.append({"flag_type": "unrecognized_doc_type", "detail": "Passport MRZ not detected — assumed TD3"})
            reason_codes.append(
                {
                    "code": "DOC_TYPE_UNRECOGNIZED",
                    "stage": 0,
                    "severity": "warning",
                    "message": "Could not detect passport MRZ format",
                }
            )

    # Classify national ID
    if ctx.id_image_path and ctx.id_raw_text:
        cls = classify_document(ctx.id_raw_text, ctx.id_image_path)
        ctx.id_doc_class = cls or "TD1"  # default ID to TD1
        details["id_class"] = ctx.id_doc_class

        if cls is None:
            flags.append({"flag_type": "unrecognized_doc_type", "detail": "National ID MRZ not detected — assumed TD1"})

    # Extract country codes from MRZ
    if ctx.passport_raw_text:
        country_match = _extract_country_from_mrz(ctx.passport_raw_text)
        if country_match:
            ctx.passport_country = country_match

    if ctx.id_raw_text:
        country_match = _extract_country_from_mrz(ctx.id_raw_text)
        if country_match:
            ctx.id_country = country_match

    # Validate issuing countries
    for label, country_code in [
        ("passport", ctx.passport_country),
        ("national_id", ctx.id_country),
    ]:
        if country_code:
            validation = await validate_issuing_country(country_code, db)
            details[f"{label}_country"] = validation

            if not validation["valid"]:
                if validation["status"] == "sanctioned":
                    hard_fail = True
                    passed = False
                    reason_codes.append(
                        {
                            "code": "SANCTIONED_COUNTRY",
                            "stage": 0,
                            "severity": "critical",
                            "message": f"{label}: {validation['detail']}",
                        }
                    )
                else:
                    flags.append({"flag_type": "country_not_approved", "detail": validation["detail"]})

            if validation.get("requires_edd"):
                flags.append({"flag_type": "edd_required", "detail": f"{label} from {country_code} requires EDD"})

    # Check document class eligibility
    for label, country, doc_class in [
        ("passport", ctx.passport_country, ctx.passport_doc_class),
        ("national_id", ctx.id_country, ctx.id_doc_class),
    ]:
        if country and doc_class:
            eligibility = await check_document_class_eligibility(country, doc_class, "idv_standard", db)
            details[f"{label}_eligibility"] = eligibility

            if not eligibility.get("eligible"):
                passed = False
                reason_codes.append(
                    {
                        "code": "DOC_CLASS_NOT_ELIGIBLE",
                        "stage": 0,
                        "severity": "error",
                        "message": eligibility["detail"],
                    }
                )

    # Structural plausibility
    for label, image_path, doc_class in [
        ("passport", ctx.passport_image_path, ctx.passport_doc_class),
        ("national_id", ctx.id_image_path, ctx.id_doc_class),
    ]:
        if image_path:
            plausibility = check_structural_plausibility(image_path, doc_class)
            details[f"{label}_structure"] = plausibility
            if not plausibility.get("plausible"):
                flags.append(
                    {
                        "flag_type": "structural_implausible",
                        "detail": plausibility["detail"],
                    }
                )

    duration = (time.time() - start) * 1000
    result = StageResult(
        stage=0,
        name="Document Acceptance & National Validity Gate",
        passed=passed,
        hard_fail=hard_fail,
        details=details,
        flags=flags,
        reason_codes=reason_codes,
        duration_ms=duration,
    )
    ctx.stage_results.append(result)
    ctx.flags.extend(flags)
    ctx.reason_codes.extend(reason_codes)
    return result


def _extract_country_from_mrz(raw_text: str) -> str | None:
    """Extract 3-letter country code from MRZ text."""
    clean = raw_text.replace(" ", "").upper()

    # TD3 line 1: P<XXX... (positions 2:5)
    td3_match = re.search(r"P[<A-Z]([A-Z]{3})", clean)
    if td3_match:
        return td3_match.group(1)

    # TD1 line 1: I<XXX... or ID<XXX...
    td1_match = re.search(r"I[DA<]([A-Z]{3})", clean)
    if td1_match:
        return td1_match.group(1)

    return None

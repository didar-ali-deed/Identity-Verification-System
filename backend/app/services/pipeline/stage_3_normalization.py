"""Stage 3 — Normalization & Cross-Zone Consistency.

Normalizes all extracted fields to canonical formats and cross-checks
VIZ vs MRZ data within each document. Hard-fails on expired documents.
"""

from __future__ import annotations

import datetime
import re
import time

import structlog

from app.services.pipeline.types import ExtractedFields, PipelineContext, StageResult

logger = structlog.get_logger()

# ICAO transliteration table (common non-Latin → Latin mappings)
ICAO_TRANSLIT = {
    "Ä": "AE",
    "Ö": "OE",
    "Ü": "UE",
    "ß": "SS",
    "É": "E",
    "È": "E",
    "Ê": "E",
    "Ë": "E",
    "À": "A",
    "Â": "A",
    "Á": "A",
    "Ç": "C",
    "Ñ": "N",
    "Ø": "OE",
    "Å": "AA",
    "Ð": "D",
    "Þ": "TH",
    "Ž": "Z",
    "Š": "S",
    "Č": "C",
}

# Name prefixes to strip for comparison
NAME_PREFIXES = {
    "MR",
    "MRS",
    "MS",
    "DR",
    "PROF",
    "SIR",
    "LADY",
    "SHEIKH",
    "SHAIKH",
    "HH",
    "HE",
}

# Father's name particles to strip
FATHER_PARTICLES = {
    "BIN",
    "BINT",
    "BINTE",
    "IBN",
    "ABU",
    "ABD",
    "ABDUL",
    "AL",
    "EL",
    "SON",
    "OF",
}


def normalize_date(raw_date: str | None) -> str | None:
    """Convert various date formats to canonical YYYYMMDD.

    Handles: YYMMDD (MRZ), DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, YYYYMMDD.
    Applies ICAO century rule: YY > current_year+10 → 1900s, else 2000s.
    """
    if not raw_date:
        return None

    raw = raw_date.strip().replace(" ", "")

    # Already canonical YYYYMMDD
    if re.match(r"^\d{8}$", raw):
        return raw

    # MRZ format: YYMMDD
    if re.match(r"^\d{6}$", raw):
        yy = int(raw[:2])
        mm = raw[2:4]
        dd = raw[4:6]
        current_yy = datetime.date.today().year % 100
        year = 1900 + yy if yy > current_yy + 10 else 2000 + yy
        return f"{year}{mm}{dd}"

    # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    match = re.match(r"^(\d{2})[/\-.](\d{2})[/\-.](\d{4})$", raw)
    if match:
        dd, mm, yyyy = match.groups()
        return f"{yyyy}{mm}{dd}"

    # YYYY/MM/DD or YYYY-MM-DD
    match = re.match(r"^(\d{4})[/\-.](\d{2})[/\-.](\d{2})$", raw)
    if match:
        yyyy, mm, dd = match.groups()
        return f"{yyyy}{mm}{dd}"

    return None


def normalize_name(raw_name: str | None) -> str | None:
    """Normalize name: uppercase, ICAO transliteration, strip prefixes, clean whitespace."""
    if not raw_name:
        return None

    name = raw_name.upper().strip()

    # Apply ICAO transliteration
    for src, dst in ICAO_TRANSLIT.items():
        name = name.replace(src.upper(), dst)

    # Strip prefixes
    tokens = name.split()
    cleaned_tokens = [t for t in tokens if t.rstrip(".") not in NAME_PREFIXES]

    # Remove non-alpha characters (except spaces and hyphens)
    result = " ".join(cleaned_tokens)
    result = re.sub(r"[^A-Z\s\-]", "", result)
    result = re.sub(r"\s+", " ", result).strip()

    return result or None


def normalize_id_number(raw_id: str | None) -> str | None:
    """Strip non-alphanumeric characters from ID number."""
    if not raw_id:
        return None
    return re.sub(r"[^A-Z0-9]", "", raw_id.upper().strip()) or None


def normalize_father_name(raw_name: str | None) -> str | None:
    """Normalize father's name, stripping common particles."""
    if not raw_name:
        return None

    name = normalize_name(raw_name)
    if not name:
        return None

    tokens = name.split()
    cleaned = [t for t in tokens if t not in FATHER_PARTICLES]

    return " ".join(cleaned).strip() or None


def cross_zone_consistency(
    mrz_fields: ExtractedFields | None,
    viz_fields: ExtractedFields | None,
) -> dict:
    """Compare VIZ vs MRZ fields within a single document.

    Returns per-field match status and overall consistency score.
    """
    if not mrz_fields or not viz_fields:
        return {"score": 1.0, "checks": {}, "detail": "Single zone only — no cross-check"}

    checks = {}
    mismatches = []

    # Name comparison (token-based after normalization)
    mrz_name = normalize_name(mrz_fields.full_name)
    viz_name = normalize_name(viz_fields.full_name)
    if mrz_name and viz_name:
        mrz_tokens = set(mrz_name.split())
        viz_tokens = set(viz_name.split())
        if mrz_tokens and viz_tokens:
            overlap = mrz_tokens & viz_tokens
            union = mrz_tokens | viz_tokens
            jaccard = len(overlap) / len(union) if union else 0.0
            name_match = jaccard >= 0.5
            checks["name"] = {
                "match": name_match,
                "mrz": mrz_name,
                "viz": viz_name,
                "jaccard": round(jaccard, 4),
            }
            if not name_match:
                mismatches.append("name")

    # Document number
    mrz_doc = normalize_id_number(mrz_fields.document_number)
    viz_doc = normalize_id_number(viz_fields.document_number)
    if mrz_doc and viz_doc:
        doc_match = mrz_doc == viz_doc
        checks["document_number"] = {
            "match": doc_match,
            "mrz": mrz_doc,
            "viz": viz_doc,
        }
        if not doc_match:
            mismatches.append("document_number")

    # DOB
    mrz_dob = normalize_date(mrz_fields.dob)
    viz_dob = normalize_date(viz_fields.dob)
    if mrz_dob and viz_dob:
        dob_match = mrz_dob == viz_dob
        checks["dob"] = {"match": dob_match, "mrz": mrz_dob, "viz": viz_dob}
        if not dob_match:
            mismatches.append("dob")

    # Expiry
    mrz_exp = normalize_date(mrz_fields.expiry_date)
    viz_exp = normalize_date(viz_fields.expiry_date)
    if mrz_exp and viz_exp:
        exp_match = mrz_exp == viz_exp
        checks["expiry_date"] = {"match": exp_match, "mrz": mrz_exp, "viz": viz_exp}
        if not exp_match:
            mismatches.append("expiry_date")

    total = len(checks)
    matched = sum(1 for c in checks.values() if c["match"])
    score = matched / max(total, 1)

    return {
        "score": round(score, 4),
        "checks": checks,
        "mismatches": mismatches,
        "detail": f"{matched}/{total} cross-zone fields match",
    }


def validate_id_structure(id_number: str | None, country: str | None) -> dict:
    """Validate identity number format against country-specific patterns."""
    if not id_number:
        return {"valid": False, "detail": "No ID number to validate"}

    clean = normalize_id_number(id_number) or ""

    # Country-specific patterns
    patterns: dict[str, tuple[str, str]] = {
        "ARE": (r"^784\d{12}$", "UAE: 784-XXXX-XXXXXXX-X (15 digits)"),
        "SAU": (r"^[12]\d{9}$", "Saudi: 1 or 2 + 9 digits"),
        "PAK": (r"^\d{13}$", "Pakistan: 13 digits (CNIC)"),
        "IND": (r"^\d{12}$", "India: 12 digits (Aadhaar)"),
        "EGY": (r"^\d{14}$", "Egypt: 14 digits"),
        "JOR": (r"^\d{10}$", "Jordan: 10 digits"),
        "GBR": (r"^\d{9}$", "UK: 9 digits (passport number)"),
    }

    if country and country.upper() in patterns:
        pattern, desc = patterns[country.upper()]
        if re.match(pattern, clean):
            # Luhn check for UAE
            if country.upper() == "ARE":
                luhn_ok = _luhn_check(clean)
                return {
                    "valid": luhn_ok,
                    "format_match": True,
                    "luhn_valid": luhn_ok,
                    "detail": f"UAE format valid, Luhn {'pass' if luhn_ok else 'fail'}",
                }
            return {"valid": True, "format_match": True, "detail": f"Matches {desc}"}
        return {
            "valid": False,
            "format_match": False,
            "detail": f"Does not match expected format: {desc}",
        }

    # Generic validation: at least 5 alphanumeric characters
    if len(clean) >= 5:
        return {"valid": True, "detail": "Generic format — no country-specific rule"}

    return {"valid": False, "detail": f"ID number too short: {len(clean)} chars"}


def check_expiry_gate(expiry_date: str | None) -> dict:
    """Hard-fail gate: reject expired documents.

    Returns dict with expired (bool), days_remaining (int), detail.
    """
    if not expiry_date:
        return {"expired": False, "days_remaining": None, "detail": "No expiry date available"}

    canonical = normalize_date(expiry_date)
    if not canonical or len(canonical) != 8:
        return {"expired": False, "days_remaining": None, "detail": "Cannot parse expiry date"}

    try:
        exp_date = datetime.date(int(canonical[:4]), int(canonical[4:6]), int(canonical[6:8]))
        today = datetime.date.today()
        delta = (exp_date - today).days

        if delta < 0:
            return {
                "expired": True,
                "days_remaining": delta,
                "expiry_date": canonical,
                "detail": f"Document expired {abs(delta)} days ago",
            }

        return {
            "expired": False,
            "days_remaining": delta,
            "expiry_date": canonical,
            "detail": f"Document valid, {delta} days remaining",
        }
    except ValueError:
        return {"expired": False, "days_remaining": None, "detail": "Invalid expiry date values"}


def _normalize_extracted_fields(fields: ExtractedFields | None) -> dict:
    """Normalize all fields in an ExtractedFields object to canonical forms."""
    if not fields:
        return {}

    return {
        "full_name": normalize_name(fields.full_name),
        "father_name": normalize_father_name(fields.father_name),
        "dob": normalize_date(fields.dob),
        "expiry_date": normalize_date(fields.expiry_date),
        "document_number": normalize_id_number(fields.document_number),
        "national_id_number": normalize_id_number(fields.national_id_number),
        "nationality": fields.nationality.upper().strip() if fields.nationality else None,
        "gender": fields.gender,
        "place_of_birth": fields.place_of_birth,
        "issuing_authority": fields.issuing_authority,
        "date_of_issue": normalize_date(fields.date_of_issue),
        "address": fields.address,
    }


async def run_stage_3(ctx: PipelineContext) -> StageResult:
    """Run Stage 3: Normalization & Cross-Zone Consistency."""
    start = time.time()
    details = {}
    flags = []
    reason_codes = []
    passed = True
    hard_fail = False

    # --- Normalize all extracted fields ---
    normalized_passport_mrz = _normalize_extracted_fields(ctx.passport_mrz_fields)
    normalized_passport_viz = _normalize_extracted_fields(ctx.passport_viz_fields)
    normalized_id_front = _normalize_extracted_fields(ctx.id_front_fields)
    normalized_id_back_mrz = _normalize_extracted_fields(ctx.id_back_mrz_fields)

    # Merge passport fields (MRZ takes precedence, VIZ fills gaps)
    ctx.normalized_passport = _merge_fields(normalized_passport_mrz, normalized_passport_viz)
    details["normalized_passport"] = ctx.normalized_passport

    # Merge ID fields (back MRZ takes precedence, front fills gaps)
    ctx.normalized_id = _merge_fields(normalized_id_back_mrz, normalized_id_front)
    details["normalized_id"] = ctx.normalized_id

    # --- Cross-zone consistency: passport VIZ vs MRZ ---
    passport_consistency = cross_zone_consistency(ctx.passport_mrz_fields, ctx.passport_viz_fields)
    details["passport_cross_zone"] = passport_consistency

    if passport_consistency.get("mismatches"):
        flags.append(
            {
                "flag_type": "viz_mrz_mismatch",
                "detail": f"Passport VIZ/MRZ mismatch on: {', '.join(passport_consistency['mismatches'])}",
            }
        )
        reason_codes.append(
            {
                "code": "VIZ_MRZ_MISMATCH",
                "stage": 3,
                "severity": "warning",
                "message": f"Passport cross-zone mismatch: {passport_consistency['mismatches']}",
            }
        )

    # --- Cross-zone consistency: national ID front vs back MRZ ---
    id_consistency = cross_zone_consistency(ctx.id_back_mrz_fields, ctx.id_front_fields)
    details["id_cross_zone"] = id_consistency

    if id_consistency.get("mismatches"):
        flags.append(
            {
                "flag_type": "viz_mrz_mismatch",
                "detail": f"ID front/back mismatch on: {', '.join(id_consistency['mismatches'])}",
            }
        )
        reason_codes.append(
            {
                "code": "VIZ_MRZ_MISMATCH",
                "stage": 3,
                "severity": "warning",
                "message": f"National ID cross-zone mismatch: {id_consistency['mismatches']}",
            }
        )

    # --- Validate ID number structure ---
    # Try passport country first, then ID country
    country = ctx.passport_country or ctx.id_country
    id_number = ctx.normalized_passport.get("national_id_number") or ctx.normalized_id.get("national_id_number")
    if id_number:
        id_validation = validate_id_structure(id_number, country)
        details["id_structure_validation"] = id_validation

        if not id_validation.get("valid"):
            flags.append(
                {
                    "flag_type": "structural_id_invalid",
                    "detail": id_validation["detail"],
                }
            )
            reason_codes.append(
                {
                    "code": "STRUCTURAL_ID_INVALID",
                    "stage": 3,
                    "severity": "warning",
                    "message": f"ID number format invalid: {id_validation['detail']}",
                }
            )

    # --- Expiry gate (hard fail if expired) ---
    for label, normalized in [
        ("passport", ctx.normalized_passport),
        ("national_id", ctx.normalized_id),
    ]:
        expiry = normalized.get("expiry_date") if normalized else None
        if expiry:
            expiry_check = check_expiry_gate(expiry)
            details[f"{label}_expiry"] = expiry_check

            if expiry_check.get("expired"):
                hard_fail = True
                passed = False
                flags.append(
                    {
                        "flag_type": "document_expired",
                        "detail": f"{label}: {expiry_check['detail']}",
                    }
                )
                reason_codes.append(
                    {
                        "code": "DOCUMENT_EXPIRED",
                        "stage": 3,
                        "severity": "critical",
                        "message": f"{label}: {expiry_check['detail']}",
                    }
                )

    duration = (time.time() - start) * 1000
    result = StageResult(
        stage=3,
        name="Normalization & Cross-Zone Consistency",
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


# --- Private helpers ---


def _merge_fields(primary: dict, secondary: dict) -> dict:
    """Merge two normalized field dicts. Primary wins on conflicts, secondary fills gaps."""
    merged = {}
    all_keys = set(list(primary.keys()) + list(secondary.keys()))
    for key in all_keys:
        val = primary.get(key)
        if val is None:
            val = secondary.get(key)
        merged[key] = val
    return merged


def _luhn_check(number: str) -> bool:
    """Validate a number string using the Luhn algorithm."""
    digits = [int(d) for d in number if d.isdigit()]
    if not digits:
        return False

    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d

    return total % 10 == 0

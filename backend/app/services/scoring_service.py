"""Identity Verification Scoring Service.

Compares passport data, ID data, and face photos to produce a total score out of 100.
Passing threshold: 90/100.
"""

import structlog

from app.config import get_settings

settings = get_settings()
logger = structlog.get_logger()

PASS_THRESHOLD = 87.0


def compute_verification_score(
    passport_ocr: dict | None,
    id_ocr: dict | None,
    face_comparisons: dict,
) -> dict:
    """Compute the total verification score.

    Args:
        passport_ocr: OCR extracted data from passport
        id_ocr: OCR extracted data from national ID (may be None)
        face_comparisons: dict with keys like 'passport_vs_selfie', 'id_vs_selfie',
                          'passport_vs_id'. Each value is a similarity float 0-1.

    Returns:
        dict with total_score, passed, and breakdown of each check.
    """
    checks = []

    # 1. Passport OCR quality (did we extract key fields?)
    if passport_ocr:
        passport_quality = _score_ocr_quality(passport_ocr, "passport")
        checks.append(passport_quality)

    # 2. ID OCR quality (if provided)
    if id_ocr:
        id_quality = _score_ocr_quality(id_ocr, "national_id")
        checks.append(id_quality)

    # 3. Data consistency: passport vs ID (if both provided)
    if passport_ocr and id_ocr:
        consistency = _score_data_consistency(passport_ocr, id_ocr)
        checks.append(consistency)

    # 4. Face: passport vs selfie
    if "passport_vs_selfie" in face_comparisons:
        score = face_comparisons["passport_vs_selfie"] * 100
        checks.append(
            {
                "name": "passport_face_vs_selfie",
                "score": round(score, 1),
                "max": 100,
                "details": f"Face similarity: {score:.1f}%",
            }
        )

    # 5. Face: ID vs selfie (if ID provided)
    if "id_vs_selfie" in face_comparisons:
        score = face_comparisons["id_vs_selfie"] * 100
        checks.append(
            {
                "name": "id_face_vs_selfie",
                "score": round(score, 1),
                "max": 100,
                "details": f"Face similarity: {score:.1f}%",
            }
        )

    # 6. Face: passport vs ID (if both provided)
    if "passport_vs_id" in face_comparisons:
        score = face_comparisons["passport_vs_id"] * 100
        checks.append(
            {
                "name": "passport_face_vs_id_face",
                "score": round(score, 1),
                "max": 100,
                "details": f"Face similarity: {score:.1f}%",
            }
        )

    # Calculate average score
    total_score = round(sum(c["score"] for c in checks) / len(checks), 1) if checks else 0.0

    passed = total_score >= PASS_THRESHOLD

    return {
        "total_score": total_score,
        "passed": passed,
        "threshold": PASS_THRESHOLD,
        "checks": checks,
        "num_checks": len(checks),
    }


def _score_ocr_quality(ocr_data: dict, doc_type: str) -> dict:
    """Score how many key fields were successfully extracted."""
    if doc_type == "passport":
        key_fields = ["full_name", "document_number", "nationality", "dob", "expiry_date", "gender"]
    else:
        key_fields = ["full_name", "national_id_number", "nationality", "dob", "expiry_date"]

    found = 0
    missing = []
    for field in key_fields:
        val = ocr_data.get(field)
        if val and str(val).strip():
            found += 1
        else:
            missing.append(field)

    score = (found / len(key_fields)) * 100 if key_fields else 0
    details = f"Extracted {found}/{len(key_fields)} fields"
    if missing:
        details += f". Missing: {', '.join(missing)}"

    return {
        "name": f"{doc_type}_ocr_quality",
        "score": round(score, 1),
        "max": 100,
        "details": details,
    }


def _score_data_consistency(passport_data: dict, id_data: dict) -> dict:
    """Compare passport and ID data fields for consistency."""
    comparisons = 0
    matches = 0
    details_parts = []

    # Compare names
    p_name = _normalize(passport_data.get("full_name", ""))
    i_name = _normalize(id_data.get("full_name", ""))
    if p_name and i_name:
        comparisons += 1
        if p_name == i_name or p_name in i_name or i_name in p_name:
            matches += 1
            details_parts.append("Name: match")
        else:
            details_parts.append(f"Name: mismatch ('{p_name}' vs '{i_name}')")

    # Compare DOB
    p_dob = passport_data.get("dob", "")
    i_dob = id_data.get("dob", "")
    if p_dob and i_dob:
        comparisons += 1
        if _normalize(str(p_dob)) == _normalize(str(i_dob)):
            matches += 1
            details_parts.append("DOB: match")
        else:
            details_parts.append(f"DOB: mismatch ('{p_dob}' vs '{i_dob}')")

    # Compare nationality
    p_nat = _normalize(passport_data.get("nationality", ""))
    i_nat = _normalize(id_data.get("nationality", ""))
    if p_nat and i_nat:
        comparisons += 1
        if p_nat == i_nat or p_nat in i_nat or i_nat in p_nat:
            matches += 1
            details_parts.append("Nationality: match")
        else:
            details_parts.append(f"Nationality: mismatch ('{p_nat}' vs '{i_nat}')")

    # Compare gender
    p_gender = _normalize(passport_data.get("gender", ""))
    i_gender = _normalize(id_data.get("gender", ""))
    if p_gender and i_gender:
        comparisons += 1
        if p_gender == i_gender:
            matches += 1
            details_parts.append("Gender: match")
        else:
            details_parts.append(f"Gender: mismatch ('{p_gender}' vs '{i_gender}')")

    score = (matches / comparisons * 100) if comparisons > 0 else 0

    return {
        "name": "data_consistency",
        "score": round(score, 1),
        "max": 100,
        "details": "; ".join(details_parts) if details_parts else "No comparable fields found",
    }


def _normalize(text: str) -> str:
    """Normalize text for comparison."""
    return " ".join(text.lower().strip().split())

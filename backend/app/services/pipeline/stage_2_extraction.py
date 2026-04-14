"""Stage 2 — Field Extraction (Dual-Zone, Dual-Document).

Extracts data from both documents independently. Each document has VIZ and MRZ zones,
extracted separately as independent data sources.
"""

from __future__ import annotations

import re
import time

import structlog

from app.config import get_settings
from app.services.ocr_service import (
    compute_field_confidence,
    extract_td1_mrz_lines,
    extract_text,
    get_raw_text,
    parse_td1_mrz,
    validate_icao_check_digit,
)
from app.services.pipeline.types import ExtractedFields, PipelineContext, StageResult

settings = get_settings()
logger = structlog.get_logger()


def extract_passport_mrz_td3(raw_text: str, ocr_results: list[dict]) -> ExtractedFields:
    """Parse TD3 passport MRZ (2 lines x 44 chars) with ICAO check digit validation."""
    fields = ExtractedFields(source="passport_mrz")
    clean = raw_text.replace(" ", "").upper()

    # Find MRZ lines
    mrz_lines = []
    for segment in re.split(r"[\n\r]+", clean):
        cleaned = re.sub(r"[^A-Z0-9<]", "", segment)
        if len(cleaned) >= 40 and "<" in cleaned:
            mrz_lines.append(cleaned)

    if len(mrz_lines) < 2:
        # Try pattern matching
        matches = re.findall(r"[A-Z0-9<]{40,48}", clean)
        if len(matches) >= 2:
            mrz_lines = matches[:2]

    if len(mrz_lines) < 2:
        return fields

    line1 = mrz_lines[0].ljust(44, "<")[:44]
    line2 = mrz_lines[1].ljust(44, "<")[:44]

    # Line 1: type(1) + subtype(1) + country(3) + name(39)
    fields.nationality = line1[2:5].replace("<", "")

    names_part = line1[5:]
    names_split = names_part.split("<<", 1)
    surname = names_split[0].replace("<", " ").strip()
    given = names_split[1].replace("<", " ").strip() if len(names_split) > 1 else ""
    fields.full_name = f"{given} {surname}".strip()

    # Line 2 layout (TD3 MRZ): positions defined by ICAO 9303 part 4
    doc_num = line2[0:9]
    doc_num_check = line2[9]
    fields.document_number = doc_num.replace("<", "")

    # Validate check digits
    doc_num_valid = validate_icao_check_digit(doc_num, doc_num_check)
    if not doc_num_valid:
        # Try common OCR corrections
        doc_num_corrected = _ocr_correct_mrz(doc_num)
        if validate_icao_check_digit(doc_num_corrected, doc_num_check):
            fields.document_number = doc_num_corrected.replace("<", "")
            doc_num_valid = True
    fields.confidences["document_number_mrz_valid"] = 1.0 if doc_num_valid else 0.0

    dob_raw = line2[13:19]
    dob_check = line2[19]
    fields.dob = _mrz_date_to_canonical(dob_raw)
    fields.confidences["dob_mrz_valid"] = 1.0 if validate_icao_check_digit(dob_raw, dob_check) else 0.0

    fields.gender = {"M": "Male", "F": "Female"}.get(line2[20], "Unknown")

    exp_raw = line2[21:27]
    exp_check = line2[27]
    fields.expiry_date = _mrz_date_to_canonical(exp_raw)
    fields.confidences["expiry_mrz_valid"] = 1.0 if validate_icao_check_digit(exp_raw, exp_check) else 0.0

    # Personal number (may contain national ID number)
    personal = line2[28:42].replace("<", "").strip()
    if personal:
        fields.national_id_number = personal

    # Composite check
    composite_data = line2[0:10] + line2[13:20] + line2[21:43]
    composite_check = line2[43]
    composite_valid = validate_icao_check_digit(composite_data, composite_check)
    fields.confidences["composite_mrz_valid"] = 1.0 if composite_valid else 0.0

    # Compute OCR confidence per field
    fields.confidences["full_name"] = compute_field_confidence(fields.full_name, ocr_results)
    fields.confidences["document_number"] = compute_field_confidence(fields.document_number, ocr_results)
    fields.confidences["nationality"] = compute_field_confidence(fields.nationality, ocr_results)

    return fields


def extract_passport_viz(raw_text: str, ocr_results: list[dict]) -> ExtractedFields:
    """Extract VIZ-only fields from passport: place_of_birth, issuing_authority, etc."""
    fields = ExtractedFields(source="passport_viz")

    # Place of birth
    pob_match = re.search(
        r"(?:place\s*of\s*birth|lieu\s*de\s*naissance)[:\s]*([A-Za-z\s\-',]+)",
        raw_text,
        re.IGNORECASE,
    )
    if pob_match:
        fields.place_of_birth = pob_match.group(1).strip()
        fields.confidences["place_of_birth"] = compute_field_confidence(fields.place_of_birth, ocr_results)

    # Date of issue
    issue_match = re.search(
        r"(?:date\s*of\s*issue|date\s*d.?emission)[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
        raw_text,
        re.IGNORECASE,
    )
    if issue_match:
        fields.date_of_issue = issue_match.group(1).strip()
        fields.confidences["date_of_issue"] = compute_field_confidence(fields.date_of_issue, ocr_results)

    # Issuing authority
    auth_match = re.search(
        r"(?:authority|autorit)[:\s]*([A-Za-z\s\-]+)",
        raw_text,
        re.IGNORECASE,
    )
    if auth_match:
        fields.issuing_authority = auth_match.group(1).strip()
        fields.confidences["issuing_authority"] = compute_field_confidence(fields.issuing_authority, ocr_results)

    # VIZ name (for cross-zone comparison)
    name_match = re.search(
        r"(?:name|nom|full\s*name|surname)[:\s]+([A-Za-z\s\-']+)",
        raw_text,
        re.IGNORECASE,
    )
    if name_match:
        fields.full_name = name_match.group(1).strip()
        fields.confidences["full_name"] = compute_field_confidence(fields.full_name, ocr_results)

    # VIZ document number
    doc_match = re.search(
        r"(?:passport|document)\s*(?:no|number|#)?[:\s]*([A-Z0-9]{6,12})",
        raw_text,
        re.IGNORECASE,
    )
    if doc_match:
        fields.document_number = doc_match.group(1).strip()

    # VIZ dates
    for pattern, field_name in [
        (r"(?:birth|dob|born)[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", "dob"),
        (r"(?:expir|valid)[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", "expiry_date"),
    ]:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            setattr(fields, field_name, match.group(1).strip())

    return fields


def extract_national_id_front(raw_text: str, ocr_results: list[dict]) -> ExtractedFields:
    """Extract fields from national ID card front side."""
    fields = ExtractedFields(source="id_front")

    # Full name
    name_patterns = [
        r"(?:name|nom|full\s*name)[:\s]+([A-Za-z\s\-']+)",
        r"(?:surname|last\s*name)[:\s]+([A-Za-z\s\-']+)",
    ]
    for pattern in name_patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            fields.full_name = match.group(1).strip()
            fields.confidences["full_name"] = compute_field_confidence(fields.full_name, ocr_results)
            break

    # Father's name
    father_patterns = [
        r"(?:father|pere|father.?s?\s*name)[:\s]+([A-Za-z\s\-']+)",
        r"(?:son\s*of|bin|ibn)[:\s]+([A-Za-z\s\-']+)",
    ]
    for pattern in father_patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            fields.father_name = match.group(1).strip()
            fields.confidences["father_name"] = compute_field_confidence(fields.father_name, ocr_results)
            break

    # National ID number
    id_patterns = [
        r"\b(\d{3}-\d{4}-\d{7}-\d)\b",  # UAE format
        r"\b(784\d{12})\b",  # UAE compact
        r"\b(\d{9,15})\b",  # Generic
    ]
    for pattern in id_patterns:
        match = re.search(pattern, raw_text)
        if match:
            fields.national_id_number = match.group(1)
            fields.confidences["national_id_number"] = compute_field_confidence(fields.national_id_number, ocr_results)
            break

    # DOB
    dob_match = re.search(
        r"(?:birth|dob|born|b\.date)[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
        raw_text,
        re.IGNORECASE,
    )
    if dob_match:
        fields.dob = dob_match.group(1).strip()
        fields.confidences["dob"] = compute_field_confidence(fields.dob, ocr_results)

    # Nationality
    nat_match = re.search(
        r"(?:nationality|citizen|nationalite)[:\s]+([A-Za-z\s]+)",
        raw_text,
        re.IGNORECASE,
    )
    if nat_match:
        fields.nationality = nat_match.group(1).strip()

    # Gender
    gender_match = re.search(r"\b(male|female|M|F)\b", raw_text, re.IGNORECASE)
    if gender_match:
        val = gender_match.group(1).upper()
        fields.gender = {"M": "Male", "F": "Female", "MALE": "Male", "FEMALE": "Female"}.get(val)

    # Expiry
    exp_match = re.search(
        r"(?:expir|valid)[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
        raw_text,
        re.IGNORECASE,
    )
    if exp_match:
        fields.expiry_date = exp_match.group(1).strip()

    return fields


def extract_national_id_back_mrz(raw_text: str, ocr_results: list[dict]) -> ExtractedFields:
    """Extract fields from national ID back using TD1 MRZ (3 x 30 chars)."""
    fields = ExtractedFields(source="id_back_mrz")

    td1_lines = extract_td1_mrz_lines(raw_text)
    if not td1_lines:
        return fields

    parsed = parse_td1_mrz(td1_lines)

    fields.full_name = parsed.get("full_name")
    fields.document_number = parsed.get("document_number")
    fields.nationality = parsed.get("nationality")
    fields.dob = parsed.get("date_of_birth")
    fields.expiry_date = parsed.get("expiry_date")
    fields.gender = parsed.get("gender")

    # Store ID number from optional fields
    opt1 = parsed.get("optional_1", "")
    opt2 = parsed.get("optional_2", "")
    if opt1:
        fields.national_id_number = opt1
    elif opt2:
        fields.national_id_number = opt2

    # Confidence based on check digit validations
    fields.confidences["document_number_mrz_valid"] = 1.0 if parsed.get("document_number_valid") else 0.0
    fields.confidences["dob_mrz_valid"] = 1.0 if parsed.get("dob_valid") else 0.0
    fields.confidences["expiry_mrz_valid"] = 1.0 if parsed.get("expiry_valid") else 0.0
    fields.confidences["composite_mrz_valid"] = 1.0 if parsed.get("composite_valid") else 0.0

    return fields


def extract_face_from_document(image_path: str, output_dir: str, doc_label: str) -> str | None:
    """Extract face from document image. Returns output path or None."""
    from app.services.face_service import save_extracted_face

    output_path = f"{output_dir}/{doc_label}_face.jpg"
    if save_extracted_face(image_path, output_path):
        return output_path
    return None


async def run_stage_2(ctx: PipelineContext) -> StageResult:
    """Run Stage 2: Field Extraction for all documents."""
    start = time.time()
    details = {}
    flags = []
    reason_codes = []
    passed = True

    # Process passport
    if ctx.passport_image_path:
        ocr_results = extract_text(ctx.passport_image_path)
        raw_text = get_raw_text(ocr_results)
        ctx.passport_ocr_results = ocr_results
        ctx.passport_raw_text = raw_text

        ctx.passport_mrz_fields = extract_passport_mrz_td3(raw_text, ocr_results)
        ctx.passport_viz_fields = extract_passport_viz(raw_text, ocr_results)

        details["passport_mrz"] = ctx.passport_mrz_fields.to_dict()
        details["passport_viz"] = ctx.passport_viz_fields.to_dict()

        # Extract face from passport
        face_path = extract_face_from_document(
            ctx.passport_image_path,
            f"./uploads/pipeline/{ctx.application_id}",
            "passport",
        )
        if face_path:
            ctx.passport_face_path = face_path
            details["passport_face_extracted"] = True
        else:
            details["passport_face_extracted"] = False
            flags.append({"flag_type": "no_face_in_doc", "detail": "No face detected in passport"})

    # Process national ID
    if ctx.id_image_path:
        ocr_results = extract_text(ctx.id_image_path)
        raw_text = get_raw_text(ocr_results)
        ctx.id_ocr_results = ocr_results
        ctx.id_raw_text = raw_text

        ctx.id_front_fields = extract_national_id_front(raw_text, ocr_results)

        # Also try TD1 MRZ from the same image (back side may be in same scan)
        ctx.id_back_mrz_fields = extract_national_id_back_mrz(raw_text, ocr_results)

        details["id_front"] = ctx.id_front_fields.to_dict()
        details["id_back_mrz"] = ctx.id_back_mrz_fields.to_dict()

        # Extract face from ID
        face_path = extract_face_from_document(
            ctx.id_image_path,
            f"./uploads/pipeline/{ctx.application_id}",
            "national_id",
        )
        if face_path:
            ctx.id_face_path = face_path
            details["id_face_extracted"] = True
        else:
            details["id_face_extracted"] = False
            flags.append({"flag_type": "no_face_in_doc", "detail": "No face detected in national ID"})

    # Check OCR confidence on anchor fields (identity number)
    anchor_fields_low = []

    for label, fields_obj in [
        ("passport_mrz", ctx.passport_mrz_fields),
        ("id_front", ctx.id_front_fields),
    ]:
        if not fields_obj:
            continue

        for field_name in ["national_id_number", "document_number"]:
            val = getattr(fields_obj, field_name, None)
            if val:
                conf = fields_obj.confidences.get(field_name, 0.0)
                if conf < settings.ocr_confidence_threshold and conf > 0.0:
                    anchor_fields_low.append(f"{label}.{field_name} conf={conf:.2f}")

    if anchor_fields_low:
        flags.append(
            {
                "flag_type": "low_ocr_confidence",
                "detail": f"Low confidence on anchor fields: {', '.join(anchor_fields_low)}",
            }
        )
        reason_codes.append(
            {
                "code": "OCR_CONFIDENCE_LOW",
                "stage": 2,
                "severity": "warning",
                "message": f"Anchor field OCR confidence below {settings.ocr_confidence_threshold}",
            }
        )

    # Build per-field confidence summary
    all_confidences = {}
    for label, fields_obj in [
        ("passport_mrz", ctx.passport_mrz_fields),
        ("passport_viz", ctx.passport_viz_fields),
        ("id_front", ctx.id_front_fields),
        ("id_back_mrz", ctx.id_back_mrz_fields),
    ]:
        if fields_obj and fields_obj.confidences:
            for k, v in fields_obj.confidences.items():
                all_confidences[f"{label}.{k}"] = v

    details["field_confidences"] = all_confidences

    duration = (time.time() - start) * 1000
    result = StageResult(
        stage=2,
        name="Field Extraction (Dual-Zone, Dual-Document)",
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


# --- Helpers ---


def _mrz_date_to_canonical(mrz_date: str) -> str | None:
    """Convert MRZ date (YYMMDD) to YYYYMMDD canonical format."""
    if len(mrz_date) != 6 or not mrz_date.isdigit():
        return None
    yy = int(mrz_date[:2])
    mm = mrz_date[2:4]
    dd = mrz_date[4:6]

    # Century resolution: per ICAO rule
    import datetime

    current_yy = datetime.date.today().year % 100
    year = 1900 + yy if yy > current_yy + 10 else 2000 + yy
    return f"{year}{mm}{dd}"


def _ocr_correct_mrz(data: str) -> str:
    """Apply common OCR corrections to MRZ characters."""
    corrections = {
        "O": "0",
        "I": "1",
        "B": "8",
        "S": "5",
        "G": "6",
    }
    result = list(data)
    for i, char in enumerate(result):
        # Only correct characters that should be digits (in numeric positions)
        if char in corrections:
            result[i] = corrections[char]
    return "".join(result)

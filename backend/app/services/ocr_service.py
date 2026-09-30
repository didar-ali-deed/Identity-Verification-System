import re
import threading
from pathlib import Path

import cv2
import numpy as np
import structlog

from app.config import get_settings
from app.utils.dates import normalize_document_date

logger = structlog.get_logger()

_easy_reader = None
_easy_lock = threading.Lock()


def _load_ocr_image(image_path: str) -> np.ndarray:
    from PIL import Image, ImageOps

    with Image.open(image_path) as source:
        image = np.asarray(ImageOps.exif_transpose(source).convert("RGB"))
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    # ID cards and passport data pages are landscape; retain originals on disk.
    if image.shape[0] > image.shape[1] * 1.2:
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    scale = min(1.0, 1800 / max(image.shape[:2]))
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return image


def _extract_easyocr(image_path: str) -> list[dict]:
    global _easy_reader
    with _easy_lock:
        if _easy_reader is None:
            import easyocr

            _easy_reader = easyocr.Reader(
                ["en"],
                gpu=get_settings().inference_use_gpu,
                model_storage_directory=str(Path.home() / ".cache" / "easyocr"),
                verbose=False,
            )
        return [
            {
                "text": str(text),
                "confidence": float(conf),
                "bbox": [[float(value) for value in point] for point in box],
                "provider": "easyocr",
            }
            for box, text, conf in _easy_reader.readtext(_load_ocr_image(image_path))
        ]


class OCRServiceError(Exception):
    pass


def extract_text(image_path: str) -> list[dict]:
    """Recognize document text with the single EasyOCR provider."""
    try:
        return _extract_easyocr(image_path)
    except Exception as exc:
        raise OCRServiceError("EasyOCR provider unavailable") from exc


def get_raw_text(ocr_results: list[dict]) -> str:
    """Combine all OCR text results into a single string."""
    return "\n".join(r["text"] for r in ocr_results if r["text"])


def _canonical_label(text: str) -> str:
    # Normalize common label glyph errors without changing any identity value.
    text = re.sub(r"\bdate\s+o[flt1]\s+", "Date of ", text, flags=re.IGNORECASE)
    return re.sub(r"\bexpury\b", "Expiry", text, flags=re.IGNORECASE)


def _label_value(rows: list[dict], label_re: str) -> str | None:
    """Pair a label with a nearby value in its column, rather than reading order."""
    for row in rows:
        parts = re.split(r"[:|]", row["text"].strip(), maxsplit=1)
        if not re.search(label_re, _canonical_label(parts[0].strip()), re.IGNORECASE):
            continue
        if len(parts) > 1 and parts[1].strip():
            return parts[1].strip()
        box = row.get("bbox")
        if not box:
            continue
        x, y = box[0]
        right, bottom = box[2]
        height = max(bottom - y, 1)
        values = []
        for candidate in rows:
            text = candidate["text"].strip()
            candidate_box = candidate.get("bbox")
            is_label = re.fullmatch(
                r"(?:name|father\s*name|given\s*names?|surname|gender|sex|nationality|country\s*of\s*stay|date\s*of\s*(?:birth|issue|expiry)|(?:passport|identity|tracking|citizenship)\s*number|place\s*of\s*birth)",
                _canonical_label(text),
                re.IGNORECASE,
            )
            if candidate is row or not candidate_box or text.endswith(":") or is_label:
                continue
            cx, cy = candidate_box[0]
            cbottom = candidate_box[2][1]
            same_row = abs((cy + cbottom) / 2 - (y + bottom) / 2) <= height * 0.6
            if same_row and cx >= right and cx - right <= height * 12:
                values.append((cx - right, text))
            elif (
                -height * 0.35 <= cy - bottom <= height * 2.5
                and (cy + cbottom) / 2 > (y + bottom) / 2 + height * 0.6
                and abs(cx - x) <= max(32, height * 1.5)
            ):
                values.append((cy - bottom, text))
        if values:
            return min(values, key=lambda item: item[0])[1]
    return None


def _clean_name(value: str | None) -> str | None:
    if not value:
        return None
    value = " ".join(value.split())
    labels = {"surname", "given names", "given name", "nationality", "date of birth", "date of expiry", "sex"}
    if value.casefold() in labels or sum(char.isalpha() for char in value) < 2:
        return None
    if any(not (char.isalpha() or char in " '-’.") for char in value):
        return None
    return value


def parse_passport(raw_text: str, ocr_results: list[dict], image_path: str = "", *, use_mrz: bool = True) -> dict:
    """Parse document text; VIZ-only mode keeps cross-zone evidence independent."""
    data: dict = {
        "document_type": "passport",
        "full_name": None,
        "dob": None,
        "document_number": None,
        "nationality": None,
        "expiry_date": None,
        "gender": None,
        "father_name": None,
        "place_of_birth": None,
        "national_id_number": None,
        "mrz_detected": False,
        "confidences": {},
    }

    mrz_lines = _extract_mrz_lines(raw_text) if use_mrz else None
    if mrz_lines:
        data["mrz_detected"] = True
        mrz = _parse_mrz(mrz_lines)
        data["full_name"] = mrz.get("full_name")
        data["document_number"] = mrz.get("document_number")
        data["nationality"] = mrz.get("nationality")
        data["dob"] = mrz.get("date_of_birth")
        data["expiry_date"] = mrz.get("expiry_date")
        data["gender"] = mrz.get("gender")

    # ── VIZ labels (Pakistan / ICAO standard) ────────────────────────────
    # Split OCR results into per-line text for label-value pairing
    lines = [r["text"].strip() for r in ocr_results if r["text"].strip()]
    joined = " ".join(lines)  # also search flat text

    def _next_val(label_re: str) -> str | None:
        """Return the value token immediately after a label in the OCR line list."""
        spatial = _label_value(ocr_results, label_re)
        if spatial is not None or any(row.get("bbox") for row in ocr_results):
            return spatial
        for i, line in enumerate(lines):
            parts = re.split(r"[:\|]", line, maxsplit=1)
            if re.search(label_re, parts[0].strip(), re.IGNORECASE):
                # Check same line after colon, or next non-empty line
                after_colon = re.split(r"[:\|]", line, maxsplit=1)
                if len(after_colon) > 1 and after_colon[1].strip():
                    return after_colon[1].strip()
                if i + 1 < len(lines):
                    return lines[i + 1].strip()
        return None

    if not data["full_name"]:
        data["full_name"] = _clean_name(_next_val(r"^(?:full\s*name|name)$"))
    if not data["full_name"]:
        surname = _clean_name(_next_val(r"^surname$"))
        given = _clean_name(_next_val(r"^given\s*names?$"))
        if surname and given:
            data["full_name"] = f"{given} {surname}".strip()
        elif surname:
            data["full_name"] = surname
        elif given:
            data["full_name"] = given

    if not data["nationality"]:
        data["nationality"] = _next_val(r"^nationality$")

    _date_re = r"\d{2}[.\-/]\d{2}[.\-/]\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}"

    if not data["dob"]:
        dob_val = _next_val(r"^date\s+of\s+birth$")
        # Only accept if the value looks like an actual date, not a label
        if dob_val and re.search(_date_re, dob_val):
            data["dob"] = dob_val
        elif not data["dob"]:
            # Search joined text for a date near "birth" keyword
            dob_m = re.search(r"(?:date\s+of\s+birth|birth\s+date)[^\d]*(" + _date_re + ")", joined, re.IGNORECASE)
            if dob_m:
                data["dob"] = dob_m.group(1)

    if not data["expiry_date"]:
        exp_val = _next_val(r"^date\s+of\s+expiry$|^expiry$")
        if exp_val and re.search(_date_re, exp_val):
            data["expiry_date"] = exp_val
        elif not data["expiry_date"]:
            exp_m = re.search(r"(?:date\s+of\s+expiry|expiry\s+date)[^\d]*(" + _date_re + ")", joined, re.IGNORECASE)
            if exp_m:
                data["expiry_date"] = exp_m.group(1)

    if not data["document_number"]:
        pn = _next_val(r"passport\s*number|^passport\s*no")
        if not pn:
            m = re.search(r"\b([A-Z]{2}\d{7})\b", joined)
            pn = m.group(1) if m else None
        data["document_number"] = pn

    father_val = _next_val(r"father|husband\s*name")
    if father_val:
        data["father_name"] = father_val

    pob_val = _next_val(r"place\s+of\s+birth")
    if pob_val:
        data["place_of_birth"] = pob_val

    # Citizenship / CNIC number
    cnic_m = re.search(r"\b(\d{5}-\d{7}-\d)\b", joined)
    if cnic_m:
        data["national_id_number"] = cnic_m.group(1)

    # Gender fallback from joined text
    if not data["gender"]:
        sex = _next_val(r"^sex$|^gender$")
        if sex and sex.upper() in ("M", "F", "MALE", "FEMALE"):
            data["gender"] = {"M": "Male", "F": "Female", "MALE": "Male", "FEMALE": "Female"}[sex.upper()]
        gm = re.search(r"\b(male|female)\b", joined, re.IGNORECASE)
        if gm:
            data["gender"] = gm.group(1).capitalize()
        else:
            gm2 = re.search(r"\bSex\b[:\s]*([MF])\b", joined, re.IGNORECASE)
            if gm2:
                data["gender"] = {"M": "Male", "F": "Female"}.get(gm2.group(1).upper())

    data["full_name"] = _clean_name(data["full_name"])
    data["father_name"] = _clean_name(data["father_name"])
    data["nationality"] = _clean_name(data["nationality"])
    return data


def parse_national_id(raw_text: str, ocr_results: list[dict]) -> dict:
    """Parse national ID / CNIC card data."""
    data: dict = {
        "document_type": "national_id",
        "full_name": None,
        "dob": None,
        "national_id_number": None,
        "father_name": None,
        "nationality": None,
        "expiry_date": None,
        "gender": None,
        "confidences": {},
    }

    lines = [r["text"].strip() for r in ocr_results if r["text"].strip()]
    joined = " ".join(lines)

    def _next_val(label_re: str) -> str | None:
        for i, line in enumerate(lines):
            if re.search(label_re, line, re.IGNORECASE):
                after_colon = re.split(r"[:\|]", line, maxsplit=1)
                if len(after_colon) > 1 and after_colon[1].strip():
                    return after_colon[1].strip()
                if i + 1 < len(lines):
                    nxt = lines[i + 1].strip()
                    # skip if next line is itself a label
                    if not re.search(r"(?:name|father|gender|identity|birth|expiry|issue)", nxt, re.IGNORECASE):
                        return nxt
        return None

    # ── Name ─────────────────────────────────────────────────────────────
    # Try label on its own line (Tesseract reads multi-line layouts this way)
    for i, line in enumerate(lines):
        if re.match(r"^\s*name\s*:?\s*$", line, re.IGNORECASE) and "father" not in line.lower():
            # Next non-empty line is the name value
            for j in range(i + 1, min(i + 3, len(lines))):
                candidate = lines[j].strip()
                # Skip Urdu/Arabic (non-ASCII)
                ascii_only = re.sub(r"[^\x00-\x7F]", "", candidate).strip()
                skip_pat = r"(?:father|mother|gender|birth|expiry|issue|identity|number)"
                if ascii_only and not re.search(skip_pat, ascii_only, re.IGNORECASE):
                    data["full_name"] = ascii_only
                    break
            if data["full_name"]:
                break

    # Fallback: "Name: Didar Ali" on same line, or "Name Didar Ali" (no father prefix)
    if not data["full_name"]:
        m = re.search(r"(?<![Ff]ather\s)(?<![Mm]other\s)\bName[:\s]+([A-Za-z][A-Za-z\s]{2,30}?)(?:\s{2,}|$)", joined)
        if m:
            data["full_name"] = m.group(1).strip()

    # ── Father name ───────────────────────────────────────────────────────
    data["father_name"] = _next_val(r"^father\s*name\s*:?\s*$|^father\s*:?\s*$")
    if not data["father_name"]:
        fm = re.search(r"[Ff]ather\s*[Nn]ame[:\s]+([A-Za-z][A-Za-z\s]{2,30}?)(?:\s{2,}|$)", joined)
        if fm:
            data["father_name"] = fm.group(1).strip()

    # ── Gender ────────────────────────────────────────────────────────────
    # CNIC layout: "Gender  Country of Stay" label row, "M  Pakistan" value row
    gm = re.search(r"\bGender\b[^a-z]*?([MF])\b", joined, re.IGNORECASE)
    if gm:
        data["gender"] = {"M": "Male", "F": "Female"}.get(gm.group(1).upper())
    else:
        gm2 = re.search(r"\b(Male|Female)\b", joined, re.IGNORECASE)
        if gm2:
            data["gender"] = gm2.group(1).capitalize()

    # ── Nationality ───────────────────────────────────────────────────────
    nat_m = re.search(r"nationality[:\s]+([A-Za-z]+)", joined, re.IGNORECASE)
    if nat_m:
        data["nationality"] = nat_m.group(1).strip()

    # ── Pakistan CNIC number ──────────────────────────────────────────────
    cnic_m = re.search(r"\b(\d{5}-\d{7}-\d)\b", joined)
    if cnic_m:
        data["national_id_number"] = cnic_m.group(1)
    if not data["national_id_number"]:
        id_val = _next_val(r"identity\s*number|id\s*number")
        if id_val:
            data["national_id_number"] = re.sub(r"\s", "", id_val)

    # ── Dates ─────────────────────────────────────────────────────────────
    _date_re = r"\d{2}[./\-]\d{2}[./\-]\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}"

    # CNIC two-column layout: "Date of Issue  Date of Expiry\n VALUE1  VALUE2"
    # The labels appear on the same line; their values appear on the next line
    # so "Date of Expiry" is followed immediately by the ISSUE date, not expiry.
    # Detect this by looking for "Date of Issue ... Date of Expiry" on the same line,
    # then capture the two dates that follow — first = issue, second = expiry.
    two_col_m = re.search(
        r"[Dd]ate\s+of\s+[Ii]ssue.*?[Dd]ate\s+of\s+[Ee]xpiry[^0-9]*"
        r"(" + _date_re + r")\D{0,15}(" + _date_re + r")",
        joined,
    )
    if two_col_m:
        # first date = issue date, second date = expiry date
        data["expiry_date"] = two_col_m.group(2)
    else:
        # Single-column layout: "Date of Expiry\n VALUE"
        exp_m = re.search(r"[Dd]ate\s+of\s+[Ee]xpiry[^0-9]*(" + _date_re + ")", joined)
        if exp_m:
            data["expiry_date"] = exp_m.group(1)

    dob_m = re.search(r"[Dd]ate\s+of\s+[Bb]irth[^0-9]*(" + _date_re + ")", joined)
    if dob_m:
        data["dob"] = dob_m.group(1)

    # Fallback: only use if 2+ distinct dates found — avoids assigning the
    # same date to both dob and expiry when only one date is on the document.
    all_dates = re.findall(_date_re, joined)
    if len(all_dates) >= 2:
        if not data["dob"]:
            data["dob"] = all_dates[0]
        if not data["expiry_date"]:
            data["expiry_date"] = all_dates[-1]

    # Column-aware values take precedence over ambiguous flattened reading order.
    for label, field in [
        (r"^name$", "full_name"),
        (r"^father\s*name$", "father_name"),
        (r"^nationality$", "nationality"),
        (r"^country\s*of\s*stay$", "country_of_stay"),
    ]:
        candidate = _clean_name(_label_value(ocr_results, label))
        if candidate:
            data[field] = candidate
    gender = _label_value(ocr_results, r"^gender$")
    if gender and gender.upper() in ("M", "F", "MALE", "FEMALE"):
        data["gender"] = {"M": "Male", "F": "Female", "MALE": "Male", "FEMALE": "Female"}[gender.upper()]
    for label, field in [(r"^date\s*of\s*birth$", "dob"), (r"^date\s*of\s*expiry$", "expiry_date")]:
        candidate = _label_value(ocr_results, label)
        match = re.search(_date_re, candidate or "")
        if match:
            data[field] = match.group()
    data["full_name"] = _clean_name(data["full_name"])
    data["father_name"] = _clean_name(data["father_name"])

    return data


def parse_drivers_license(raw_text: str, ocr_results: list[dict]) -> dict:
    """Parse driver's license data from OCR text."""
    data: dict = {
        "document_type": "drivers_license",
        "full_name": None,
        "dob": None,
        "document_number": None,
        "expiry_date": None,
        "confidences": {},
    }

    lines = [r["text"].strip() for r in ocr_results if r["text"].strip()]
    joined = " ".join(lines)

    data.update(_extract_from_viz(raw_text))
    if data.get("date_of_birth"):
        data["dob"] = data.pop("date_of_birth")

    date_map: dict = {}
    _extract_dates_from_text(joined, date_map)
    if not data["dob"]:
        data["dob"] = date_map.get("date_of_birth")
    if not data["expiry_date"]:
        data["expiry_date"] = date_map.get("expiry_date")

    lic_patterns = [
        r"(?:license|licence|lic)\s*(?:no|number|#)?[:\s]*([A-Z0-9-]+)",
        r"\b([A-Z]{1,2}\d{6,10})\b",
    ]
    for pattern in lic_patterns:
        m = re.search(pattern, joined, re.IGNORECASE)
        if m:
            data["document_number"] = m.group(1).strip()
            break

    return data


def parse_document(raw_text: str, ocr_results: list[dict], doc_type: str, image_path: str = "") -> dict:
    """Route to the appropriate parser based on document type."""
    if doc_type == "passport":
        return parse_passport(raw_text, ocr_results, image_path=image_path)
    if doc_type == "national_id":
        return parse_national_id(raw_text, ocr_results)
    if doc_type == "drivers_license":
        return parse_drivers_license(raw_text, ocr_results)
    raise OCRServiceError(f"Unsupported document type: {doc_type}")


# --- Private helpers ---


def _is_valid_mrz_line(line: str) -> bool:
    """Return True only if a cleaned string plausibly is a real MRZ line.

    TD3 line 2 can contain no fillers when its optional data is populated.
    The name line must start with P< and contain the surname separator.
    """
    if len(line) == 44 and re.fullmatch(r"[A-Z0-9<]{9}\d[A-Z<]{3}\d{6}\d[MF<]\d{6}\d[A-Z0-9<]{14}\d\d", line):
        return True
    if len(line) < 40 or line.count("<") < 5 or not line.startswith("P<"):
        return False
    # Reject lines that look like label/word concatenations (no consecutive '<')
    # Real MRZ line 1 has '<<' between surname and given names
    # Real MRZ line 2 has runs of '<<' at the end
    return "<<" in line


def _extract_mrz_lines(text: str) -> list[str] | None:
    """Attempt to find MRZ lines (two lines of ~44 chars with < characters)."""
    lines = text.replace(" ", "").split("\n")
    mrz_candidates = []

    for line in lines:
        cleaned = re.sub(r"[^A-Z0-9<]", "", line.upper())
        if len(cleaned) >= 40 and _is_valid_mrz_line(cleaned):
            mrz_candidates.append(cleaned)

    # Also try finding MRZ pattern in the full text
    if len(mrz_candidates) < 2:
        mrz_pattern = r"([A-Z0-9<]{40,44})"
        matches = re.findall(mrz_pattern, text.replace(" ", "").upper())
        valid_matches = [m for m in matches if _is_valid_mrz_line(m)]
        mrz_candidates = valid_matches[:2] if len(valid_matches) >= 2 else mrz_candidates

    return mrz_candidates if len(mrz_candidates) >= 2 else None


def _parse_mrz(mrz_lines: list[str]) -> dict:
    """Parse TD3 format MRZ (passport — two lines of 44 chars).

    Validates positional structure before trusting any field.
    Line 1 must start with a document-type indicator (P, V, I) followed by '<'.
    """
    data = {}
    try:
        line1 = mrz_lines[0].ljust(44, "<")
        line2 = mrz_lines[1].ljust(44, "<")

        # Sanity check: line1[0] must be a document type code letter
        if line1[0] not in "PVIAC" or line1[1] != "<":
            # Not a valid TD3 MRZ — bail out so VIZ fallback is used instead
            return data

        # Line 1: P<COUNTRY<SURNAME<<GIVEN_NAMES
        # Country code: positions 2-4 (must be 3 uppercase letters)
        country = line1[2:5].replace("<", "")
        if not re.match(r"^[A-Z]{1,3}$", country):
            return data

        names_part = line1[5:]
        names_split = names_part.split("<<", 1)
        surname = names_split[0].replace("<", " ").strip()
        given = names_split[1].replace("<", " ").strip() if len(names_split) > 1 else ""
        full_name = f"{given} {surname}".strip()

        # Reject clearly garbage names (contain known label words)
        _label_words = {"SURNAME", "GIVEN", "NAMES", "NATION", "BIRTH", "EXPIRY", "BOOKLET", "CITIZEN"}
        if any(w in full_name.upper().split() for w in _label_words):
            return data

        data["full_name"] = full_name
        data["nationality"] = country

        # Line 2: DOC_NUMBER(9) + CHECK(1) + NATIONALITY(3) + DOB(6) + CHECK(1) + GENDER(1) + EXPIRY(6) + CHECK(1)
        data["document_number"] = line2[0:9].replace("<", "")
        dob_raw = line2[13:19]
        data["date_of_birth"] = normalize_document_date(dob_raw)
        data["gender"] = {"M": "Male", "F": "Female"}.get(line2[20], "Unknown")
        exp_raw = line2[21:27]
        data["expiry_date"] = normalize_document_date(exp_raw)

    except (IndexError, ValueError):
        pass

    return data


def _extract_from_viz(text: str) -> dict:
    """Fallback VIZ extraction via regex (used by drivers_license)."""
    data: dict = {}

    # Name — exclude "Father Name" / "Mother Name"
    name_m = re.search(r"(?<![Ff]ather\s)(?<![Mm]other\s)\bName[:\s]+([A-Za-z\s\-']+)", text)
    if not name_m:
        name_m = re.search(r"(?:full\s*name|surname)[:\s]+([A-Za-z\s\-']+)", text, re.IGNORECASE)
    if name_m:
        data["full_name"] = name_m.group(1).strip()

    # Document number
    for pat in [r"(?:passport|document|license)\s*(?:no|number|#)?[:\s]*([A-Z0-9]{6,12})", r"\b([A-Z]{1,2}\d{6,9})\b"]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            data["document_number"] = m.group(1).strip()
            break

    nat_m = re.search(r"(?:nationality|citizen)[:\s]+([A-Za-z\s]+)", text, re.IGNORECASE)
    if nat_m:
        data["nationality"] = nat_m.group(1).strip()

    gm = re.search(r"\b(male|female)\b", text, re.IGNORECASE)
    if gm:
        data["gender"] = gm.group(1).capitalize()

    return data


def _extract_dates_from_text(text: str, data: dict) -> None:
    """Extract date of birth and expiry date from text."""
    date_patterns = [
        r"(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",  # DD/MM/YYYY
        r"(\d{4}[/\-\.]\d{2}[/\-\.]\d{2})",  # YYYY/MM/DD
        r"(\d{2}\s+\w+\s+\d{4})",  # 01 Jan 2030
    ]

    dates_found = []
    for pattern in date_patterns:
        dates_found.extend(re.findall(pattern, text))

    # Map dates to fields using context
    for date_str in dates_found:
        # Check surrounding context
        idx = text.find(date_str)
        context_before = text[max(0, idx - 40) : idx].lower() if idx > 0 else ""

        if any(kw in context_before for kw in ["birth", "dob", "born", "b.date"]):
            if not data.get("date_of_birth"):
                data["date_of_birth"] = date_str
        elif any(kw in context_before for kw in ["expir", "valid", "exp"]):
            if not data.get("expiry_date"):
                data["expiry_date"] = date_str
        elif any(kw in context_before for kw in ["issue", "issued"]) and not data.get("issue_date"):
            data["issue_date"] = date_str

    # If we have dates but couldn't assign them contextually
    unassigned = [
        d for d in dates_found if d not in [data.get("date_of_birth"), data.get("expiry_date"), data.get("issue_date")]
    ]
    if unassigned and not data.get("date_of_birth"):
        data["date_of_birth"] = unassigned[0]
    if len(unassigned) > 1 and not data.get("expiry_date"):
        data["expiry_date"] = unassigned[1]


# --- ICAO 9303 MRZ check digit validation ---

_ICAO_WEIGHTS = [7, 3, 1]

_ICAO_CHAR_VALUES: dict[str, int] = {
    "<": 0,
    "0": 0,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
}
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _ICAO_CHAR_VALUES[_c] = 10 + _i


def validate_icao_check_digit(data: str, check_char: str) -> bool:
    """Validate ICAO 9303 check digit using weighted 7-3-1 modulus-10.

    Args:
        data: The field data string (uppercase, only A-Z, 0-9, <).
        check_char: The single check digit character.

    Returns:
        True if the check digit is valid.
    """
    if not check_char or len(check_char) != 1:
        return False
    try:
        expected = int(check_char)
    except ValueError:
        return False

    total = 0
    for i, char in enumerate(data.upper()):
        val = _ICAO_CHAR_VALUES.get(char, 0)
        weight = _ICAO_WEIGHTS[i % 3]
        total += val * weight

    return (total % 10) == expected


# --- TD1 MRZ parsing (National ID cards: 3 lines x 30 chars) ---


def extract_td1_mrz_lines(text: str) -> list[str] | None:
    """Detect TD1 MRZ (3 lines of ~30 chars with < characters)."""
    lines = text.replace(" ", "").split("\n")
    mrz_candidates = []

    for line in lines:
        cleaned = re.sub(r"[^A-Z0-9<]", "", line.upper())
        if 26 <= len(cleaned) <= 34 and "<" in cleaned:
            mrz_candidates.append(cleaned)

    # Also search full text
    if len(mrz_candidates) < 3:
        pattern = r"([A-Z0-9<]{26,34})"
        matches = re.findall(pattern, text.replace(" ", "").upper())
        if len(matches) >= 3:
            mrz_candidates = matches[:3]

    return mrz_candidates if len(mrz_candidates) >= 3 else None


def parse_td1_mrz(mrz_lines: list[str]) -> dict:
    """Parse TD1 format MRZ (national ID card — three lines of 30 chars).

    TD1 layout:
      Line 1: doc_type(2) + country(3) + doc_number(9) + check(1) + optional(15)
      Line 2: dob(6) + check(1) + sex(1) + expiry(6) + check(1) + nationality(3) + optional(11)
      Line 3: name (surname<<given_names)
    """
    data = {}
    try:
        line1 = mrz_lines[0].ljust(30, "<")
        line2 = mrz_lines[1].ljust(30, "<")
        line3 = mrz_lines[2].ljust(30, "<")

        # Line 1
        data["document_type_code"] = line1[0:2].replace("<", "")
        data["issuing_country"] = line1[2:5].replace("<", "")
        doc_num = line1[5:14]
        doc_num_check = line1[14]
        data["document_number"] = doc_num.replace("<", "")
        data["document_number_valid"] = validate_icao_check_digit(doc_num, doc_num_check)
        data["optional_1"] = line1[15:30].replace("<", "").strip() or None

        # Line 2
        dob_raw = line2[0:6]
        dob_check = line2[6]
        data["date_of_birth"] = normalize_document_date(dob_raw)
        data["dob_valid"] = validate_icao_check_digit(dob_raw, dob_check)
        data["gender"] = {"M": "Male", "F": "Female"}.get(line2[7], "Unknown")
        exp_raw = line2[8:14]
        exp_check = line2[14]
        data["expiry_date"] = normalize_document_date(exp_raw)
        data["expiry_valid"] = validate_icao_check_digit(exp_raw, exp_check)
        data["nationality"] = line2[15:18].replace("<", "")
        data["optional_2"] = line2[18:29].replace("<", "").strip() or None

        # Composite check digit (line 2 position 29)
        composite_data = line1[5:30] + line2[0:7] + line2[8:15] + line2[18:29]
        composite_check = line2[29]
        data["composite_valid"] = validate_icao_check_digit(composite_data, composite_check)

        # Line 3: names
        names_part = line3
        names_split = names_part.split("<<", 1)
        surname = names_split[0].replace("<", " ").strip()
        given = names_split[1].replace("<", " ").strip() if len(names_split) > 1 else ""
        data["full_name"] = f"{given} {surname}".strip()

    except (IndexError, ValueError):
        pass

    return data


# --- OCR with confidence per-field ---


def compute_field_confidence(
    field_value: str | None,
    ocr_results: list[dict],
) -> float:
    """Find the OCR result that best matches a field value and return its confidence.

    Returns 0.0 if no match found, or the highest confidence of matching segments.
    """
    if not field_value or not ocr_results:
        return 0.0

    normalized_value = field_value.lower().strip()
    if not normalized_value:
        return 0.0

    best_confidence = 0.0
    for result in ocr_results:
        result_text = result["text"].lower().strip()
        if not result_text:
            continue
        # Exact or substring match
        if normalized_value in result_text:
            confidence = float(result["confidence"])
            if np.isfinite(confidence) and 0 <= confidence <= 1:
                best_confidence = max(best_confidence, confidence)

    return round(best_confidence, 4)

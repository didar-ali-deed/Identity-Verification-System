import re
import threading
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import structlog

logger = structlog.get_logger()

# ── TrOCR singleton ───────────────────────────────────────────────────────────
# microsoft/trocr-base-printed: fast, accurate for printed document text.
# Downloaded from HuggingFace on first use (~400 MB), cached in container volume.
_ocr_lock = threading.Lock()
_ocr_processor = None
_ocr_model = None
_ocr_device = None


def _get_ocr():
    """Thread-safe lazy initialiser — loads TrOCR exactly once per process."""
    global _ocr_processor, _ocr_model, _ocr_device
    if _ocr_model is None:
        with _ocr_lock:
            if _ocr_model is None:
                import logging  # noqa: PLC0415
                import torch  # noqa: PLC0415
                from transformers import TrOCRProcessor, VisionEncoderDecoderModel  # noqa: PLC0415

                logging.getLogger("transformers").setLevel(logging.ERROR)
                _ocr_device = "cuda" if torch.cuda.is_available() else "cpu"
                _ocr_processor = TrOCRProcessor.from_pretrained(
                    "microsoft/trocr-base-printed"
                )
                _ocr_model = VisionEncoderDecoderModel.from_pretrained(
                    "microsoft/trocr-base-printed"
                ).to(_ocr_device)
                _ocr_model.eval()
    return _ocr_processor, _ocr_model, _ocr_device


def _recognize_pil(pil_image):
    """Run TrOCR on a single PIL image crop. Returns (text, confidence)."""
    import torch  # noqa: PLC0415
    from PIL import Image as PILImage  # noqa: PLC0415

    processor, model, device = _get_ocr()
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")
    pixel_values = processor(images=pil_image, return_tensors="pt").pixel_values.to(device)
    with torch.no_grad():
        generated_ids = model.generate(pixel_values)
    text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
    return text, 0.95  # TrOCR doesn't expose per-token confidence; use fixed high value


def _detect_text_regions(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Detect candidate text-line bounding boxes using morphological operations."""
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 4))
    dilated = cv2.dilate(binary, kernel, iterations=1)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w >= 30 and h >= 8:
            regions.append((x, y, w, h))
    # Sort top-to-bottom, then left-to-right
    regions.sort(key=lambda r: (r[1], r[0]))
    return regions


class OCRServiceError(Exception):
    def __init__(self, detail: str):
        self.detail = detail


def preprocess_image(image_path: str) -> np.ndarray:
    """Load and enhance image for downstream use (kept for backward-compat)."""
    img = cv2.imread(image_path)
    if img is None:
        raise OCRServiceError("Failed to read image file")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def extract_text(image_path: str) -> list[dict]:
    """Extract text from a document image using TrOCR.

    Detects text-line regions with OpenCV morphology, then recognises each
    line with microsoft/trocr-base-printed.
    Returns list of {text, confidence, bbox} dicts — same shape as before.
    """
    if not Path(image_path).exists():
        raise OCRServiceError("Image file not found")

    from PIL import Image as PILImage  # noqa: PLC0415

    img = cv2.imread(image_path)
    if img is None:
        raise OCRServiceError("Failed to read image file")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    regions = _detect_text_regions(gray)

    output: list[dict] = []
    for x, y, w, h in regions:
        crop_bgr = img[y : y + h, x : x + w]
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil_crop = PILImage.fromarray(crop_rgb)
        text, conf = _recognize_pil(pil_crop)
        if text:
            box = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
            output.append({"text": text, "confidence": conf, "bbox": box})

    return output


def extract_mrz_zone(image_path: str) -> str:
    """Crop the bottom 22% of the document (MRZ zone) and run TrOCR.

    Returns raw MRZ text — typically two or three lines of A-Z 0-9 < characters.
    """
    from PIL import Image as PILImage  # noqa: PLC0415

    img = cv2.imread(image_path)
    if img is None:
        return ""
    h, w = img.shape[:2]
    mrz_strip = img[int(h * 0.78) :, :]

    if w < 1400:
        scale = 1400 / w
        mrz_strip = cv2.resize(mrz_strip, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(mrz_strip, cv2.COLOR_BGR2GRAY)
    regions = _detect_text_regions(gray)

    lines: list[str] = []
    for x, y, rw, rh in regions:
        crop = mrz_strip[y : y + rh, x : x + rw]
        pil_crop = PILImage.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        text, _ = _recognize_pil(pil_crop)
        cleaned = re.sub(r"[^A-Z0-9<]", "", text.upper().replace(" ", ""))
        if len(cleaned) >= 30 and "<<" in cleaned:
            lines.append(cleaned)

    return "\n".join(lines)


def get_raw_text(ocr_results: list[dict]) -> str:
    """Combine all OCR text results into a single string."""
    return " ".join(r["text"] for r in ocr_results if r["text"])


def parse_passport(raw_text: str, ocr_results: list[dict], image_path: str = "") -> dict:
    """Parse passport data. Tries MRZ zone first (most reliable), then VIZ fallback."""
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

    # ── MRZ — dedicated zone crop with Tesseract MRZ whitelist ───────────
    mrz_raw = extract_mrz_zone(image_path) if image_path else ""
    mrz_lines = _extract_mrz_lines(mrz_raw) or _extract_mrz_lines(raw_text)
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
        for i, line in enumerate(lines):
            if re.search(label_re, line, re.IGNORECASE):
                # Check same line after colon, or next non-empty line
                after_colon = re.split(r"[:\|]", line, maxsplit=1)
                if len(after_colon) > 1 and after_colon[1].strip():
                    return after_colon[1].strip()
                if i + 1 < len(lines):
                    return lines[i + 1].strip()
        return None

    if not data["full_name"]:
        surname = _next_val(r"^surname$")
        given = _next_val(r"^given\s*names?$")
        if surname and given:
            data["full_name"] = f"{given} {surname}".strip()
        elif surname:
            data["full_name"] = surname
        elif given:
            data["full_name"] = given

    if not data["nationality"]:
        data["nationality"] = _next_val(r"^nationality$")

    _date_re = r"\d{2}[.\-/]\d{2}[.\-/]\d{4}|\d{4}-\d{2}-\d{2}"

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
        gm = re.search(r"\b(male|female)\b", joined, re.IGNORECASE)
        if gm:
            data["gender"] = gm.group(1).capitalize()
        else:
            gm2 = re.search(r"\bSex\b[:\s]*([MF])\b", joined, re.IGNORECASE)
            if gm2:
                data["gender"] = {"M": "Male", "F": "Female"}.get(gm2.group(1).upper())

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
    nat_m = re.search(r"(?:nationality|country\s+of\s+stay)[:\s]+([A-Za-z]+)", joined, re.IGNORECASE)
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
    _date_re = r"\d{2}[./\-]\d{2}[./\-]\d{4}"

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


def validate_expiry(parsed_data: dict) -> dict:
    """Check if the document is expired. Returns validation result."""
    expiry_str = parsed_data.get("expiry_date")
    if not expiry_str:
        return {"is_expired": None, "message": "Expiry date not detected"}

    try:
        expiry = _parse_date_string(expiry_str)
        if not expiry:
            return {"is_expired": None, "message": "Could not parse expiry date"}

        is_expired = expiry.replace(tzinfo=UTC) < datetime.now(UTC)
        return {
            "is_expired": is_expired,
            "expiry_date": expiry.strftime("%Y-%m-%d"),
            "message": "Document has expired" if is_expired else "Document is valid",
        }
    except Exception:
        return {"is_expired": None, "message": "Expiry date validation failed"}


# --- Private helpers ---


def _is_valid_mrz_line(line: str) -> bool:
    """Return True only if a cleaned string plausibly is a real MRZ line.

    Real TD3 passport MRZ lines have:
    - Exactly 44 chars (we're lenient: 42-44)
    - At least 8 fill '<' characters (real lines have many)
    - Line 1 always starts with a document-type letter + '<' (e.g. 'P<')
    - Line 2 starts with a digit (doc number) or letter but NOT a long word
    """
    if len(line) < 40 or line.count("<") < 5:
        return False
    # Reject lines that look like label/word concatenations (no consecutive '<')
    # Real MRZ line 1 has '<<' between surname and given names
    # Real MRZ line 2 has runs of '<<' at the end
    if "<<" not in line:
        return False
    return True


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
        data["date_of_birth"] = _mrz_date_to_string(dob_raw)
        data["gender"] = {"M": "Male", "F": "Female"}.get(line2[20], "Unknown")
        exp_raw = line2[21:27]
        data["expiry_date"] = _mrz_date_to_string(exp_raw)

    except (IndexError, ValueError):
        pass

    return data


def _mrz_date_to_string(mrz_date: str) -> str | None:
    """Convert MRZ date (YYMMDD) to canonical YYYYMMDD format.

    Uses ICAO century rule: if YY > current_year+10 → 1900s, else 2000s.
    Output is YYYYMMDD (no dashes) — consistent with stage_2_extraction.
    """
    if len(mrz_date) != 6 or not mrz_date.isdigit():
        return None
    import datetime as _dt
    yy = int(mrz_date[:2])
    mm = mrz_date[2:4]
    dd = mrz_date[4:6]
    current_yy = _dt.date.today().year % 100
    year = 1900 + yy if yy > current_yy + 10 else 2000 + yy
    return f"{year}{mm}{dd}"


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


def _parse_date_string(date_str: str) -> datetime | None:
    """Attempt to parse a date string in various formats."""
    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%d %b %Y",
        "%d %B %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


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


def compute_icao_check_digit(data: str) -> int:
    """Compute the ICAO 9303 check digit for a field."""
    total = 0
    for i, char in enumerate(data.upper()):
        val = _ICAO_CHAR_VALUES.get(char, 0)
        weight = _ICAO_WEIGHTS[i % 3]
        total += val * weight
    return total % 10


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
        data["date_of_birth"] = _mrz_date_to_string(dob_raw)
        data["dob_valid"] = validate_icao_check_digit(dob_raw, dob_check)
        data["gender"] = {"M": "Male", "F": "Female"}.get(line2[7], "Unknown")
        exp_raw = line2[8:14]
        exp_check = line2[14]
        data["expiry_date"] = _mrz_date_to_string(exp_raw)
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


def extract_text_with_bboxes(image_path: str) -> tuple[list[dict], str]:
    """Extract text with full bbox + confidence info. Returns (results, raw_text)."""
    results = extract_text(image_path)
    raw_text = get_raw_text(results)
    return results, raw_text


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
        if normalized_value in result_text or result_text in normalized_value:
            best_confidence = max(best_confidence, result["confidence"])

    return round(best_confidence, 4)

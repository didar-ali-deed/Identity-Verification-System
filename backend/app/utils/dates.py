"""Document date formats shared by OCR and pipeline normalization."""

import re
from datetime import datetime


def parse_document_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.isdigit() and len(text) not in (6, 8):
        return None
    if re.fullmatch(r"\d{6}", text):
        year = int(text[:2])
        century = 1900 if year > datetime.now().year % 100 + 10 else 2000
        text = f"{century + year}{text[2:]}"
    for pattern in (
        "%Y%m%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def normalize_document_date(value: str | None) -> str | None:
    date = parse_document_date(value)
    return date.strftime("%Y%m%d") if date else None

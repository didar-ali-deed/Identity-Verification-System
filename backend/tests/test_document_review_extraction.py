from app.services.ocr_service import parse_national_id, parse_passport


def test_populated_mrz_second_line_preserves_line_boundaries():
    from app.services.ocr_service import _is_valid_mrz_line, get_raw_text

    line = "XX0000000" + "0" + "PAK" + "900201" + "0" + "M" + "340101" + "0" + "00000000000000" + "00"
    assert len(line) == 44
    assert _is_valid_mrz_line(line)
    assert get_raw_text([{"text": "first"}, {"text": line}]) == "first\n" + line


def test_passport_label_typos_and_overlapping_boxes():
    def row(text, y):
        return {"text": text, "confidence": 0.9, "bbox": [[100, y], [280, y], [280, y + 30], [100, y + 30]]}

    rows = [
        row("Surname", 10),
        row("SAMPLE", 37),
        row("Given Names", 90),
        row("ALEX", 117),
        row("Date ol Birth", 170),
        row("01 FEB 1990", 197),
        row("Date of Expury", 250),
        row("01 FEB 2034", 277),
    ]
    result = parse_passport("\n".join(r["text"] for r in rows), rows)
    assert result["full_name"] == "ALEX SAMPLE"
    assert result["dob"] == "01 FEB 1990"
    assert result["expiry_date"] == "01 FEB 2034"


def parse_lines(*texts):
    rows = [{"text": text, "confidence": 0.9} for text in texts]
    return parse_passport("\n".join(texts), rows)


def test_passport_does_not_treat_ocr_noise_as_identity():
    result = parse_lines("Surname", "-7 :", "Nationality", "^")
    assert result["full_name"] is None
    assert result["nationality"] is None


def test_passport_reads_inline_labels():
    result = parse_lines("Surname: SAMPLE", "Given Names: ALEX", "Nationality: PAKISTANI", "Date of Birth: 01/02/1990")
    assert result["full_name"] == "ALEX SAMPLE"
    assert result["nationality"] == "PAKISTANI"
    assert result["dob"] == "01/02/1990"


def test_passport_does_not_use_next_label_as_a_name():
    result = parse_lines("Surname", "Given Names", "Nationality", "PAKISTANI")
    assert result["full_name"] is None


def test_passport_accepts_dates_with_month_names():
    result = parse_lines("Date of Birth: 02 FEB 1990", "Date of Expiry: 08 FEB 2034")
    assert result["dob"] == "02 FEB 1990"
    assert result["expiry_date"] == "08 FEB 2034"


def test_passport_values_remain_in_their_columns():
    def row(text, x, y):
        return {"text": text, "confidence": 0.9, "bbox": [[x, y], [x + 180, y], [x + 180, y + 25], [x, y + 25]]}

    rows = [
        row("Surname:", 100, 100),
        row("Date of Birth:", 600, 100),
        row("SAMPLE", 100, 135),
        row("01.02.1990", 600, 135),
        row("Given Names:", 100, 190),
        row("Passport Number:", 600, 190),
        row("ALEX", 100, 225),
        row("XX0000000", 600, 225),
    ]
    result = parse_passport("\n".join(r["text"] for r in rows), rows)
    assert result["full_name"] == "ALEX SAMPLE"
    assert result["document_number"] == "XX0000000"
    assert result["dob"] == "01.02.1990"


def test_national_id_dates_and_gender_use_their_own_column():
    def row(text, x, y):
        return {"text": text, "confidence": 0.9, "bbox": [[x, y], [x + 180, y], [x + 180, y + 25], [x, y + 25]]}

    rows = [
        row("Identity Number", 100, 100),
        row("Date of Birth", 600, 100),
        row("00000-0000000-0", 100, 135),
        row("01.02.1990", 600, 135),
        row("Date of Issue", 100, 200),
        row("Date of Expiry", 600, 200),
        row("01.01.2024", 100, 235),
        row("01.01.2034", 600, 235),
        row("Gender", 100, 300),
        row("Country of Stay", 600, 300),
        row("M", 100, 335),
        row("Pakistan", 600, 335),
    ]
    result = parse_national_id(" ".join(r["text"] for r in rows), rows)
    assert result["dob"] == "01.02.1990"
    assert result["expiry_date"] == "01.01.2034"
    assert result["gender"] == "Male"
    assert result["country_of_stay"] == "Pakistan"
    assert result["nationality"] is None

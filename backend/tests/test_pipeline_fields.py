import pytest

from app.services.pipeline.stage_2_extraction import extract_national_id_front, extract_passport_viz
from app.services.pipeline.stage_5_similarity import run_stage_5
from app.services.pipeline.stage_7_hard_rules import evaluate_hard_rules
from app.services.pipeline.stage_8_decision import compute_decision
from app.services.pipeline.types import PipelineContext


def test_pipeline_uses_shared_spatial_parser_and_normalizes_month_dates():
    from app.services.ocr_service import parse_national_id, parse_passport
    from app.services.pipeline.stage_3_normalization import normalize_date

    def row(text, y):
        return {"text": text, "confidence": 0.95, "bbox": [[10, y], [210, y], [210, y + 25], [10, y + 25]]}

    passport_rows = [
        row("Surname", 0),
        row("SAMPLE", 28),
        row("Given Names", 70),
        row("ALEX", 98),
        row("Date of Birth", 140),
        row("01 FEB 1990", 168),
        row("Date of Expiry", 210),
        row("01 FEB 2034", 238),
    ]
    id_rows = [
        row("Name", 0),
        row("Alex Sample", 28),
        row("Date of Birth", 70),
        row("01.02.1990", 98),
        row("Date of Expiry", 140),
        row("01.02.2035", 168),
    ]
    for rows, parser, extractor in [
        (passport_rows, parse_passport, extract_passport_viz),
        (id_rows, parse_national_id, extract_national_id_front),
    ]:
        text = "\n".join(r["text"] for r in rows)
        review = parser(text, rows)
        pipeline = extractor(text, rows)
        for field in ("full_name", "dob", "expiry_date"):
            assert getattr(pipeline, field) == review[field]
        assert normalize_date(pipeline.dob) == "19900201"
    assert normalize_date("01 FEB 2034") == "20340201"


def test_field_extraction_stops_at_line_boundaries():
    fields = extract_national_id_front("Name: Alex Sample\nDOB: 01/01/1990\nNationality: Pakistan", [])
    assert fields.full_name == "Alex Sample"
    assert fields.nationality == "Pakistan"


def test_pakistan_cross_document_fields_are_extracted():
    text = "Name: Alex Sample\nFather's Name: Jamie Sample\nIdentity Number: 12345-1234567-1"
    for extractor in (extract_passport_viz, extract_national_id_front):
        fields = extractor(text, [])
        assert fields.father_name == "Jamie Sample"
        assert fields.national_id_number == "12345-1234567-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("dob,expected", [("19900102", "REJECTED"), ("19900110", "MANUAL_REVIEW")])
async def test_dob_mismatch_cannot_be_rescued_by_other_scores(monkeypatch, dob, expected):
    from app.services.pipeline import stage_5_similarity

    monkeypatch.setattr(stage_5_similarity, "compute_channel_a", lambda _: {"score": 1.0, "verified": True})
    identity = {
        "full_name": "ALEX SAMPLE",
        "national_id_number": "123456789",
        "father_name": "JAMIE SAMPLE",
        "dob": "19900101",
    }
    ctx = PipelineContext(
        application_id="synthetic", normalized_passport=identity, normalized_id={**identity, "dob": dob}
    )
    await run_stage_5(ctx)
    assert compute_decision(0.99, evaluate_hard_rules(ctx)["override"]) == expected

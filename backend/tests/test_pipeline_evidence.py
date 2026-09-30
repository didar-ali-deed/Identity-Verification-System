import math

import pytest

from app.services import face_service, passive_liveness
from app.services.ocr_service import compute_field_confidence, extract_text
from app.services.pipeline.stage_1_liveness import check_selfie_liveness
from app.services.pipeline.stage_5_similarity import (
    compute_channel_a,
    compute_channel_b,
    compute_channel_c,
    compute_channel_d,
    compute_channel_e,
)
from app.services.pipeline.stage_7_hard_rules import evaluate_hard_rules, run_stage_7
from app.services.pipeline.stage_8_decision import compute_decision
from app.services.pipeline.types import PipelineContext, StageResult


def complete_context():
    ctx = PipelineContext(application_id="synthetic", weighted_total=0.99)
    ctx.stage_results = [StageResult(stage=index, name=str(index), passed=True) for index in range(7)]
    ctx.stage_results[1].details = {"selfie_liveness": {"is_live": True, "verified": True}}
    ctx.stage_results[5].details = {"channel_a_biometric": {"verified": True}}
    return ctx


def test_liveness_exception_never_passes(monkeypatch):
    def unavailable(_):
        raise RuntimeError("Model unavailable")

    monkeypatch.setattr(face_service, "compute_lbp_texture_score", unavailable)
    result = check_selfie_liveness("synthetic.jpg")
    assert result["is_live"] is False
    assert result["verified"] is False


def test_zero_texture_cannot_be_rescued_by_basic_validation(monkeypatch):
    monkeypatch.setattr(face_service, "compute_lbp_texture_score", lambda _: 0.0)
    monkeypatch.setattr(face_service, "validate_selfie", lambda _: {"is_valid": True})
    monkeypatch.setattr(face_service, "check_face_proportions", lambda _: {"is_normal": True})
    assert check_selfie_liveness("synthetic.jpg")["is_live"] is False


@pytest.mark.parametrize("scores", [[0.99, 0.20, 0.99], [0.99, math.nan, 0.99]])
def test_every_frame_must_pass(monkeypatch, scores):
    values = iter(scores)
    monkeypatch.setattr(passive_liveness, "score_frame", lambda _: next(values))
    assert passive_liveness.check_frames(["a", "b", "c"])["is_live"] is False


def test_three_good_frames_pass(monkeypatch):
    monkeypatch.setattr(passive_liveness, "score_frame", lambda _: 0.95)
    result = passive_liveness.check_frames(["a", "b", "c"])
    assert result["verified"] is True
    assert result["frame_count"] == 3


def test_model_exception_blocks_multiframe_approval(monkeypatch):
    def unavailable(_):
        raise RuntimeError("Weights unavailable")

    monkeypatch.setattr(passive_liveness, "score_frame", unavailable)
    assert passive_liveness.check_frames(["a", "b", "c"])["verified"] is False


@pytest.mark.parametrize("count", [0, 1, 2, 11])
def test_invalid_frame_count_fails(count):
    assert passive_liveness.check_frames(["frame"] * count)["is_live"] is False


@pytest.mark.parametrize("channel", [compute_channel_b, compute_channel_c, compute_channel_d, compute_channel_e])
def test_one_document_does_not_receive_perfect_cross_document_score(channel):
    ctx = PipelineContext(
        application_id="synthetic",
        normalized_passport={
            "national_id_number": "DEMO-001",
            "full_name": "ALEX SAMPLE",
            "father_name": "JAMIE SAMPLE",
            "dob": "19900101",
        },
    )
    assert channel(ctx)["score"] == 0


def test_failed_second_face_comparison_is_not_ignored(monkeypatch):
    ctx = PipelineContext(
        application_id="synthetic",
        passport_image_path="passport",
        id_image_path="id",
        selfie_image_path="selfie",
        passport_face_path="face",
    )
    monkeypatch.setattr(
        face_service,
        "compare_faces",
        lambda *_: {
            "similarity_score": 0.99,
            "verified": True,
            "is_match": True,
        },
    )
    result = compute_channel_a(ctx)
    assert result["verified"] is False
    assert result["score"] == 0


@pytest.mark.asyncio
async def test_missing_stages_cannot_approve():
    ctx = PipelineContext(application_id="synthetic", weighted_total=1)
    await run_stage_7(ctx)
    assert compute_decision(ctx.weighted_total, ctx.decision_override) == "REJECTED"


@pytest.mark.asyncio
async def test_heuristics_always_require_review():
    ctx = complete_context()
    ctx.stage_results[1].details["selfie_liveness"]["verified"] = False
    await run_stage_7(ctx)
    assert compute_decision(ctx.weighted_total, ctx.decision_override) == "MANUAL_REVIEW"


@pytest.mark.asyncio
async def test_verified_evidence_can_approve():
    ctx = complete_context()
    await run_stage_7(ctx)
    assert compute_decision(ctx.weighted_total, ctx.decision_override) == "APPROVED"


@pytest.mark.parametrize(
    "flag,expected",
    [
        ("id_mismatch", "REJECTED"),
        ("selfie_liveness_fail", "REJECTED"),
        ("biometric_unverified", "REJECTED"),
        ("low_ocr_confidence", "MANUAL_REVIEW"),
        ("country_not_approved", "MANUAL_REVIEW"),
        ("class_not_eligible", "REJECTED"),
        ("document_expired", "REJECTED"),
        ("watchlist_hit", "MANUAL_REVIEW"),
    ],
)
def test_rules_override_a_perfect_score(flag, expected):
    ctx = PipelineContext(application_id="synthetic", flags=[{"flag_type": flag}])
    assert compute_decision(1, evaluate_hard_rules(ctx)["override"]) == expected


@pytest.mark.parametrize("score", [math.nan, math.inf, -0.1, 1.1])
def test_invalid_scores_never_approve(score):
    assert compute_decision(score, None) == "REJECTED"


def test_partial_text_cannot_supply_confidence_for_full_field():
    assert compute_field_confidence("ALEX SAMPLE", [{"text": "ALEX", "confidence": 0.99}]) == 0


def test_single_ocr_provider_failure_is_explicit(monkeypatch):
    from app.services import ocr_service

    def unavailable(_):
        raise RuntimeError("Provider unavailable")

    monkeypatch.setattr(ocr_service, "_extract_easyocr", unavailable)
    with pytest.raises(ocr_service.OCRServiceError, match="EasyOCR provider unavailable"):
        extract_text("synthetic")

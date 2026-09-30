import sys
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.services import face_service


@pytest.fixture
def comparison(monkeypatch, tmp_path):
    path = tmp_path / "face.png"
    cv2.imwrite(str(path), np.full((80, 80, 3), 100, dtype=np.uint8))
    monkeypatch.setattr(face_service.settings, "face_backend", "deepface")
    face = {"x": 10, "y": 10, "width": 40, "height": 40, "confidence": 0.99}
    monkeypatch.setattr(face_service, "detect_faces", lambda _: [face])
    return str(path)


def test_comparison_uses_detected_crops(comparison, monkeypatch):
    def verify(**kwargs):
        assert isinstance(kwargs["img1_path"], np.ndarray)
        assert kwargs["img1_path"].shape[:2] == (56, 56)
        assert kwargs["detector_backend"] == "skip"
        assert kwargs["enforce_detection"] is True
        return {"distance": 0.1, "threshold": 0.4, "verified": True}

    monkeypatch.setitem(sys.modules, "deepface", SimpleNamespace(DeepFace=SimpleNamespace(verify=verify)))
    assert face_service.compare_faces(comparison, comparison)["verified"] is True


@pytest.mark.parametrize("count", [0, 2])
def test_comparison_rejects_missing_or_multiple_faces(comparison, monkeypatch, count):
    monkeypatch.setitem(sys.modules, "deepface", SimpleNamespace(DeepFace=SimpleNamespace()))
    monkeypatch.setattr(face_service, "detect_faces", lambda _: [{}] * count)
    with pytest.raises(face_service.FaceServiceError, match="exactly one"):
        face_service.compare_faces(comparison, comparison)


def test_comparison_preserves_wrapped_model_error(comparison, monkeypatch):
    def verify(**kwargs):
        try:
            raise ValueError("Invalid embedding shape")
        except ValueError as cause:
            raise ValueError("Exception while processing img1_path") from cause

    monkeypatch.setitem(sys.modules, "deepface", SimpleNamespace(DeepFace=SimpleNamespace(verify=verify)))
    with pytest.raises(face_service.FaceServiceError, match="Invalid embedding shape"):
        face_service.compare_faces(comparison, comparison)

"""Fail-closed, multi-frame MiniFASNet adapter. Models remain external artifacts."""

import sys
from pathlib import Path
from threading import Lock

import cv2
import numpy as np

from app.config import get_settings

_models = None
_cropper = None
_lock = Lock()


def _load_models():
    global _models, _cropper
    if _models is not None:
        return _models, _cropper
    settings = get_settings()
    repo = Path(settings.silent_face_repo).resolve()
    weights = sorted(Path(settings.silent_face_model_dir).glob("*.pth"))
    if not (repo / "src").is_dir() or not weights:
        raise RuntimeError("MiniFASNet repository or weights missing; see docs/models.md")
    sys.path.insert(0, str(repo))
    import torch
    from src.anti_spoof_predict import AntiSpoofPredict
    from src.generate_patches import CropImage
    from src.utility import parse_model_name

    class CachedPredictor(AntiSpoofPredict):
        def __init__(self, path):
            self.device = torch.device("cuda:0" if settings.inference_use_gpu and torch.cuda.is_available() else "cpu")
            self.path = str(path)
            super()._load_model(self.path)

        def _load_model(self, path):
            if path != self.path:
                raise ValueError("Unexpected anti-spoof model path")

    loaded = []
    for path in weights:
        height, width, _, scale = parse_model_name(path.name)
        loaded.append((CachedPredictor(path), str(path), height, width, scale))
    _cropper = CropImage()
    _models = loaded
    return _models, _cropper


def score_frame(path: str) -> float:
    from app.services.face_service import detect_faces

    image = cv2.imread(path)
    if image is None:
        raise ValueError("Cannot read selfie frame")
    faces = detect_faces(path)
    if len(faces) != 1:
        return 0.0
    face = faces[0]
    bbox = [face["x"], face["y"], face["width"], face["height"]]
    if not np.isfinite(bbox).all() or bbox[2] <= 0 or bbox[3] <= 0:
        return 0.0
    with _lock:
        models, cropper = _load_models()
        scores = []
        for predictor, model_path, height, width, scale in models:
            patch = cropper.crop(image, bbox, scale, width, height, crop=scale is not None)
            prediction = np.asarray(predictor.predict(patch, model_path))
            if prediction.shape != (1, 3):
                raise RuntimeError("Unexpected MiniFASNet output shape")
            score = float(prediction[0, 1])
            if not np.isfinite(score) or not 0 <= score <= 1:
                raise RuntimeError("Invalid MiniFASNet output")
            scores.append(score)
        return float(np.mean(scores))


def check_frames(paths: list[str]) -> dict:
    """No frame or provider error may be rescued by a successful frame."""
    if not 3 <= len(paths) <= 10:
        return {"score": 0.0, "is_live": False, "verified": False, "detail": "Require 3–10 selfie frames"}
    try:
        scores = [score_frame(path) for path in paths]
        valid = all(np.isfinite(score) and 0 <= score <= 1 for score in scores)
        passed = valid and min(scores) >= get_settings().liveness_threshold
        return {
            "score": round(min(scores), 4) if valid else 0.0,
            "frame_scores": scores,
            "is_live": passed,
            "verified": passed,
            "provider": "minifasnet",
            "frame_count": len(scores),
            "threshold": get_settings().liveness_threshold,
            "detail": "Every frame passed passive liveness" if passed else "Passive liveness failed",
        }
    except Exception:
        return {
            "score": 0.0,
            "is_live": False,
            "verified": False,
            "provider": "minifasnet",
            "detail": "Passive liveness unavailable; no approval can be issued",
        }

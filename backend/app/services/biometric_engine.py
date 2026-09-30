"""Optional InsightFace backend, adapted from the E:\\ID_V verification engine."""

from threading import Lock

import cv2
import numpy as np

from app.config import get_settings

_engine = None
_lock = Lock()


def _get_engine():
    global _engine
    if _engine is None:
        from insightface.app import FaceAnalysis

        gpu = get_settings().inference_use_gpu
        _engine = FaceAnalysis(
            name="buffalo_l",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"] if gpu else ["CPUExecutionProvider"],
        )
        _engine.prepare(ctx_id=0 if gpu else -1, det_size=(640, 640))
    return _engine


def detect(image: np.ndarray) -> list:
    with _lock:
        return _get_engine().get(image)


def compare(first: str, second: str) -> dict:
    embeddings = []
    for path in (first, second):
        image = cv2.imread(path)
        if image is None:
            raise ValueError("Cannot read face image")
        faces = detect(image)
        if len(faces) != 1:
            raise ValueError("Exactly one face is required in each image")
        embeddings.append(np.asarray(faces[0].normed_embedding, dtype=float))
    similarity = float(np.dot(*embeddings))
    if not np.isfinite(similarity):
        raise ValueError("Invalid face similarity")
    similarity = round(max(0.0, min(1.0, similarity)), 4)
    threshold = get_settings().face_similarity_threshold
    return {
        "similarity_score": similarity,
        "distance": round(1.0 - similarity, 4),
        "threshold": threshold,
        "verified": similarity >= threshold,
        "is_match": similarity >= threshold,
        "model": "insightface/buffalo_l",
    }

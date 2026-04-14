from pathlib import Path

import cv2
import numpy as np
import structlog

from app.config import get_settings

settings = get_settings()
logger = structlog.get_logger()

# Lazy-loaded detector
_face_detector = None


def _get_face_detector():
    """Lazy-initialize MediaPipe FaceDetector (new Task API)."""
    global _face_detector
    if _face_detector is None:
        import mediapipe as mp

        base_options = mp.tasks.BaseOptions(
            model_asset_path=_get_model_path(),
        )
        options = mp.tasks.vision.FaceDetectorOptions(
            base_options=base_options,
            min_detection_confidence=0.5,
        )
        _face_detector = mp.tasks.vision.FaceDetector.create_from_options(options)
        logger.msg("MediaPipe FaceDetector initialized (Task API)")
    return _face_detector


def _get_model_path() -> str:
    """Download or locate the BlazeFace model file."""
    import urllib.request

    model_dir = Path(__file__).parent.parent / "models_data"
    model_dir.mkdir(exist_ok=True)
    model_path = model_dir / "blaze_face_short_range.tflite"

    if not model_path.exists():
        url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
        logger.msg("Downloading BlazeFace model...")
        urllib.request.urlretrieve(url, str(model_path))
        logger.msg("BlazeFace model downloaded", path=str(model_path))

    return str(model_path)


class FaceServiceError(Exception):
    def __init__(self, detail: str):
        self.detail = detail


def detect_faces(image_path: str) -> list[dict]:
    """Detect all faces in an image using MediaPipe Task API.

    Returns list of dicts with: bbox (x, y, w, h in pixels), confidence.
    """
    import mediapipe as mp

    img = _read_image(image_path)
    h, w = img.shape[:2]
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
    detector = _get_face_detector()
    result = detector.detect(mp_image)

    faces = []
    for detection in result.detections:
        bbox = detection.bounding_box
        faces.append(
            {
                "x": bbox.origin_x,
                "y": bbox.origin_y,
                "width": bbox.width,
                "height": bbox.height,
                "x_norm": round(bbox.origin_x / w, 4),
                "y_norm": round(bbox.origin_y / h, 4),
                "width_norm": round(bbox.width / w, 4),
                "height_norm": round(bbox.height / h, 4),
                "confidence": round(float(detection.categories[0].score), 4),
            }
        )

    return faces


def extract_face(image_path: str, padding: float = 0.2) -> np.ndarray | None:
    """Extract and crop the primary face from an image.

    Returns the cropped face as a numpy array, or None if no face found.
    """
    img = _read_image(image_path)
    h, w = img.shape[:2]

    faces = detect_faces(image_path)
    if not faces:
        return None

    # Use the most confident detection
    best = max(faces, key=lambda f: f["confidence"])
    bx, by, bw, bh = best["x"], best["y"], best["width"], best["height"]

    # Add padding
    pad_w = int(bw * padding)
    pad_h = int(bh * padding)
    x1 = max(0, bx - pad_w)
    y1 = max(0, by - pad_h)
    x2 = min(w, bx + bw + pad_w)
    y2 = min(h, by + bh + pad_h)

    face_crop = img[y1:y2, x1:x2]
    if face_crop.size == 0:
        return None

    return face_crop


def save_extracted_face(image_path: str, output_path: str) -> bool:
    """Extract face from image and save to output path.

    Returns True if face was found and saved.
    """
    face = extract_face(image_path)
    if face is None:
        return False

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(output_path, face)
    return True


def compare_faces(
    image1_path: str,
    image2_path: str,
    model_name: str = "Facenet",
) -> dict:
    """Compare two face images and return similarity result.

    Uses DeepFace for face comparison.
    Returns dict with: verified, distance, threshold, model, similarity_score, is_match.
    """
    if not Path(image1_path).exists():
        raise FaceServiceError("First image not found")
    if not Path(image2_path).exists():
        raise FaceServiceError("Second image not found")

    try:
        from deepface import DeepFace

        result = DeepFace.verify(
            img1_path=image1_path,
            img2_path=image2_path,
            model_name=model_name,
            enforce_detection=False,
            detector_backend="opencv",
        )

        distance = float(result["distance"])
        threshold = float(result["threshold"])

        # Convert distance to similarity score (0 to 1, higher = more similar)
        similarity = max(0.0, 1.0 - (distance / (threshold * 2)))
        similarity = round(min(1.0, similarity), 4)

        is_match = similarity >= settings.face_similarity_threshold

        return {
            "verified": bool(result["verified"]),
            "distance": round(distance, 4),
            "threshold": round(threshold, 4),
            "model": model_name,
            "similarity_score": similarity,
            "is_match": is_match,
        }

    except ValueError as e:
        raise FaceServiceError(f"Face comparison failed: {e}") from e
    except Exception as e:
        logger.error("Face comparison error", error=str(e))
        raise FaceServiceError("Face comparison failed due to an internal error") from e


def validate_selfie(image_path: str) -> dict:
    """Run basic selfie validation checks.

    Checks: single face, face size ratio, image brightness.
    """
    img = _read_image(image_path)
    h, w = img.shape[:2]

    checks = {
        "has_face": False,
        "single_face": False,
        "face_size_ok": False,
        "brightness_ok": False,
        "is_valid": False,
        "issues": [],
    }

    faces = detect_faces(image_path)

    if not faces:
        checks["issues"].append("No face detected in selfie")
        return checks

    checks["has_face"] = True

    if len(faces) > 1:
        checks["issues"].append(f"Multiple faces detected ({len(faces)}). Selfie must contain only your face")
    else:
        checks["single_face"] = True

    # Face size ratio check
    best = max(faces, key=lambda f: f["confidence"])
    face_area_ratio = best["width_norm"] * best["height_norm"]
    if face_area_ratio < 0.03:
        checks["issues"].append("Face is too far from camera. Please move closer")
    elif face_area_ratio > 0.8:
        checks["issues"].append("Face is too close. Please move back slightly")
    else:
        checks["face_size_ok"] = True

    # Brightness check
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(np.mean(gray))
    if mean_brightness < 40:
        checks["issues"].append("Image is too dark. Please improve lighting")
    elif mean_brightness > 240:
        checks["issues"].append("Image is overexposed. Please reduce lighting")
    else:
        checks["brightness_ok"] = True

    checks["is_valid"] = all(
        [
            checks["has_face"],
            checks["single_face"],
            checks["face_size_ok"],
            checks["brightness_ok"],
        ]
    )

    return checks


def validate_document_face(image_path: str) -> dict:
    """Validate that a document image contains a detectable face."""
    faces = detect_faces(image_path)

    return {
        "has_face": len(faces) > 0,
        "face_count": len(faces),
        "confidence": faces[0]["confidence"] if faces else 0.0,
        "message": (
            "Face detected in document" if faces else "No face detected in document. Please upload a clearer image"
        ),
    }


# --- Private helpers ---


def compute_lbp_texture_score(image_path: str) -> float:
    """Compute LBP (Local Binary Pattern) texture score as a liveness heuristic.

    Real faces exhibit richer micro-texture patterns than flat photo printouts
    or screen replays. A higher score indicates more natural texture (more likely live).

    Returns a score between 0.0 and 1.0.
    """
    img = _read_image(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    faces = detect_faces(image_path)
    if not faces:
        return 0.0

    best = max(faces, key=lambda f: f["confidence"])
    bx, by, bw, bh = best["x"], best["y"], best["width"], best["height"]
    h, w = gray.shape[:2]
    x1 = max(0, bx)
    y1 = max(0, by)
    x2 = min(w, bx + bw)
    y2 = min(h, by + bh)
    face_region = gray[y1:y2, x1:x2]

    if face_region.size == 0:
        return 0.0

    # Compute LBP manually (simplified 8-neighbor)
    face_resized = cv2.resize(face_region, (128, 128))
    lbp = np.zeros_like(face_resized, dtype=np.uint8)

    for i in range(1, face_resized.shape[0] - 1):
        for j in range(1, face_resized.shape[1] - 1):
            center = face_resized[i, j]
            code = 0
            code |= (int(face_resized[i - 1, j - 1]) >= int(center)) << 7
            code |= (int(face_resized[i - 1, j]) >= int(center)) << 6
            code |= (int(face_resized[i - 1, j + 1]) >= int(center)) << 5
            code |= (int(face_resized[i, j + 1]) >= int(center)) << 4
            code |= (int(face_resized[i + 1, j + 1]) >= int(center)) << 3
            code |= (int(face_resized[i + 1, j]) >= int(center)) << 2
            code |= (int(face_resized[i + 1, j - 1]) >= int(center)) << 1
            code |= (int(face_resized[i, j - 1]) >= int(center)) << 0
            lbp[i, j] = code

    # Compute histogram of LBP values
    hist, _ = np.histogram(lbp.ravel(), bins=256, range=(0, 256))
    hist = hist.astype(float)
    hist /= hist.sum() + 1e-7

    # Entropy of LBP histogram — higher entropy = more texture variety = more likely real
    entropy = -np.sum(hist * np.log2(hist + 1e-7))
    max_entropy = np.log2(256)  # ~8.0

    # Normalize to 0-1 scale
    score = min(1.0, entropy / max_entropy)
    return round(score, 4)


def check_face_proportions(image_path: str) -> dict:
    """Check face proportion characteristics for anomaly detection.

    Verifies face occupies a reasonable proportion and has expected aspect ratio.
    """
    img = _read_image(image_path)
    h, w = img.shape[:2]
    faces = detect_faces(image_path)

    if not faces:
        return {
            "has_face": False,
            "face_ratio": 0.0,
            "aspect_ratio": 0.0,
            "is_normal": False,
            "issues": ["No face detected"],
        }

    best = max(faces, key=lambda f: f["confidence"])
    face_area = best["width_norm"] * best["height_norm"]
    aspect = best["width"] / max(best["height"], 1)

    issues = []
    if face_area < 0.01:
        issues.append("Face too small — possible distant/fake photo")
    if face_area > 0.85:
        issues.append("Face fills too much of frame — possible close-up crop")
    if aspect < 0.5 or aspect > 1.2:
        issues.append(f"Unusual face aspect ratio: {aspect:.2f}")

    return {
        "has_face": True,
        "face_ratio": round(face_area, 4),
        "aspect_ratio": round(aspect, 4),
        "is_normal": len(issues) == 0,
        "issues": issues,
    }


# --- Private helpers ---


def _read_image(image_path: str) -> np.ndarray:
    """Read image from disk with validation."""
    if not Path(image_path).exists():
        raise FaceServiceError(f"Image file not found: {image_path}")

    img = cv2.imread(image_path)
    if img is None:
        raise FaceServiceError("Failed to read image file")

    return img

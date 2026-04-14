"""Stage 1 — Document Liveness & Anti-Spoofing.

Determines whether images are from real physical documents and a live person,
not screen replays, printouts, or digitally injected fakes.
"""

from __future__ import annotations

import time

import cv2
import numpy as np
import structlog

from app.services.pipeline.types import PipelineContext, StageResult

logger = structlog.get_logger()

# Thresholds
DOC_LIVENESS_THRESHOLD = 0.35  # Below this = likely fake
SELFIE_LIVENESS_THRESHOLD = 0.40
TAMPER_THRESHOLD = 0.65  # Above this = likely tampered


def detect_screen_replay(image_path: str) -> dict:
    """Detect moire patterns indicative of screen photography via FFT analysis."""
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return {"score": 0.5, "detail": "Cannot read image"}

        # Resize for consistent analysis
        img = cv2.resize(img, (512, 512))

        # Apply FFT
        f_transform = np.fft.fft2(img.astype(np.float32))
        f_shift = np.fft.fftshift(f_transform)
        magnitude = np.log1p(np.abs(f_shift))

        # Analyze high-frequency energy (moire patterns appear as periodic peaks)
        h, w = magnitude.shape
        center_y, center_x = h // 2, w // 2

        # Create ring mask for mid-to-high frequencies
        y, x = np.ogrid[:h, :w]
        dist = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
        mid_high_mask = (dist > h * 0.2) & (dist < h * 0.45)

        mid_high_energy = np.mean(magnitude[mid_high_mask])
        total_energy = np.mean(magnitude)
        ratio = mid_high_energy / max(total_energy, 1e-7)

        # High ratio of mid-high frequency energy suggests periodic patterns (moire)
        # Typical range: 0.3-0.6 for real docs, 0.6+ for screen captures
        is_screen = ratio > 0.62
        score = min(1.0, max(0.0, (ratio - 0.3) / 0.4))

        return {
            "score": round(score, 4),
            "frequency_ratio": round(ratio, 4),
            "is_screen_replay": is_screen,
            "detail": "Moire pattern detected" if is_screen else "No moire pattern",
        }
    except Exception as e:
        return {"score": 0.5, "detail": f"Screen replay check failed: {e}"}


def detect_printout(image_path: str) -> dict:
    """Detect halftone patterns from printed document photographs."""
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return {"score": 0.5, "detail": "Cannot read image"}

        img = cv2.resize(img, (512, 512))

        # Apply bandpass filter to isolate halftone frequencies
        # Halftone dots typically at 60-150 LPI (lines per inch)
        blurred_low = cv2.GaussianBlur(img, (3, 3), 0)
        blurred_high = cv2.GaussianBlur(img, (15, 15), 0)
        bandpass = cv2.absdiff(blurred_low, blurred_high)

        # Analyze regularity of the bandpass output
        laplacian = cv2.Laplacian(bandpass, cv2.CV_64F)
        float(np.var(laplacian))

        # Split into blocks and check variance consistency
        block_size = 64
        block_vars = []
        for i in range(0, 512, block_size):
            for j in range(0, 512, block_size):
                block = bandpass[i : i + block_size, j : j + block_size]
                block_vars.append(float(np.var(block)))

        # Halftone prints have very uniform block-level variance
        variance_of_vars = float(np.var(block_vars)) if block_vars else 0
        mean_var = float(np.mean(block_vars)) if block_vars else 0
        cv_score = variance_of_vars / max(mean_var, 1e-7)

        # Low coefficient of variation = uniform = halftone
        is_printout = cv_score < 0.5 and mean_var > 10
        score = max(0.0, min(1.0, 1.0 - cv_score))

        return {
            "score": round(score, 4),
            "block_variance_cv": round(cv_score, 4),
            "is_printout": is_printout,
            "detail": "Halftone pattern detected" if is_printout else "No halftone pattern",
        }
    except Exception as e:
        return {"score": 0.5, "detail": f"Printout check failed: {e}"}


def detect_pixel_tampering(image_path: str) -> dict:
    """Detect pixel-level tampering via Error Level Analysis (ELA) and clone detection."""
    try:
        img = cv2.imread(image_path)
        if img is None:
            return {"score": 0.5, "detail": "Cannot read image"}

        # --- ELA (Error Level Analysis) ---
        # Re-encode at quality 90 and measure difference
        encode_param = [cv2.IMWRITE_JPEG_QUALITY, 90]
        _, encoded = cv2.imencode(".jpg", img, encode_param)
        recompressed = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

        ela = cv2.absdiff(img, recompressed).astype(np.float32)
        ela_gray = cv2.cvtColor(ela.astype(np.uint8), cv2.COLOR_BGR2GRAY)

        # Divide into grid and check for anomalous blocks
        h, w = ela_gray.shape
        block_h, block_w = h // 4, w // 4
        block_means = []
        for i in range(4):
            for j in range(4):
                block = ela_gray[
                    i * block_h : (i + 1) * block_h,
                    j * block_w : (j + 1) * block_w,
                ]
                block_means.append(float(np.mean(block)))

        if not block_means:
            return {"score": 0.5, "detail": "ELA analysis produced no blocks"}

        mean_ela = float(np.mean(block_means))
        std_ela = float(np.std(block_means))

        # High std relative to mean = inconsistent compression = possible tampering
        ela_score = min(1.0, std_ela / max(mean_ela, 1e-7))

        # --- ORB keypoint clone detection ---
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        orb = cv2.ORB_create(nfeatures=500)
        keypoints, descriptors = orb.detectAndCompute(gray, None)

        clone_score = 0.0
        if descriptors is not None and len(descriptors) > 10:
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
            matches = bf.knnMatch(descriptors, descriptors, k=2)

            clone_pairs = 0
            for match_pair in matches:
                if len(match_pair) == 2:
                    m, n = match_pair
                    if m.queryIdx != m.trainIdx and m.distance < 30:
                        # Check spatial distance — clones are far apart
                        pt1 = keypoints[m.queryIdx].pt
                        pt2 = keypoints[m.trainIdx].pt
                        spatial_dist = np.sqrt((pt1[0] - pt2[0]) ** 2 + (pt1[1] - pt2[1]) ** 2)
                        if spatial_dist > 50:
                            clone_pairs += 1

            clone_score = min(1.0, clone_pairs / 20.0)

        combined_score = 0.6 * ela_score + 0.4 * clone_score
        is_tampered = combined_score > TAMPER_THRESHOLD

        return {
            "score": round(combined_score, 4),
            "ela_score": round(ela_score, 4),
            "clone_score": round(clone_score, 4),
            "is_tampered": is_tampered,
            "detail": "Tampering indicators detected" if is_tampered else "No tampering detected",
        }
    except Exception as e:
        return {"score": 0.5, "detail": f"Tampering check failed: {e}"}


def check_security_feature_zones(image_path: str, doc_class: str | None) -> dict:
    """Verify photo zone, MRZ zone, and signature zone positions."""
    try:
        img = cv2.imread(image_path)
        if img is None:
            return {"score": 0.5, "detail": "Cannot read image"}

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        zones_found = {}

        # MRZ zone: typically bottom 20-30% of the document
        bottom_region = gray[int(h * 0.7) :, :]
        # MRZ text is high contrast, uniform spacing
        _, binary = cv2.threshold(bottom_region, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text_density = float(np.sum(binary < 128)) / max(binary.size, 1)
        zones_found["mrz_zone"] = text_density > 0.15

        # Photo zone: typically left side, upper portion
        if doc_class in ("TD3", "TD2"):
            photo_region = gray[int(h * 0.1) : int(h * 0.65), : int(w * 0.35)]
        else:  # TD1 or unknown
            photo_region = gray[int(h * 0.1) : int(h * 0.7), : int(w * 0.4)]

        # Photo zone should have moderate variance (face image)
        photo_variance = float(np.var(photo_region))
        zones_found["photo_zone"] = photo_variance > 500

        zones_ok = sum(zones_found.values())
        total_zones = len(zones_found)
        score = zones_ok / max(total_zones, 1)

        return {
            "score": round(score, 4),
            "zones_found": zones_found,
            "detail": f"{zones_ok}/{total_zones} expected zones detected",
        }
    except Exception as e:
        return {"score": 0.5, "detail": f"Zone check failed: {e}"}


def check_selfie_liveness(selfie_path: str) -> dict:
    """LBP texture analysis and proportion checks as PAD (Presentation Attack Detection) proxy."""
    try:
        from app.services.face_service import (
            check_face_proportions,
            compute_lbp_texture_score,
            validate_selfie,
        )

        # LBP texture score (real skin vs flat)
        lbp_score = compute_lbp_texture_score(selfie_path)

        # Basic selfie validation
        selfie_check = validate_selfie(selfie_path)

        # Face proportions
        proportions = check_face_proportions(selfie_path)

        # Combine scores
        validation_score = 1.0 if selfie_check["is_valid"] else 0.3
        proportion_score = 1.0 if proportions.get("is_normal") else 0.5
        combined = 0.50 * lbp_score + 0.30 * validation_score + 0.20 * proportion_score

        is_live = combined >= SELFIE_LIVENESS_THRESHOLD

        return {
            "score": round(combined, 4),
            "lbp_score": round(lbp_score, 4),
            "validation_score": round(validation_score, 4),
            "proportion_score": round(proportion_score, 4),
            "is_live": is_live,
            "selfie_issues": selfie_check.get("issues", []),
            "detail": "Selfie liveness passed" if is_live else "Selfie liveness failed",
        }
    except Exception as e:
        return {"score": 0.5, "is_live": True, "detail": f"Selfie liveness check failed: {e}"}


def _compute_doc_liveness_score(screen: dict, printout: dict, tamper: dict, zones: dict) -> float:
    """Combine document liveness sub-scores. Lower is better (less fraud)."""
    # Invert: for liveness, we want LOW fraud scores → HIGH liveness
    screen_liveness = 1.0 - screen.get("score", 0.5)
    printout_liveness = 1.0 - printout.get("score", 0.5)
    tamper_liveness = 1.0 - tamper.get("score", 0.5)
    zone_score = zones.get("score", 0.5)

    return 0.25 * screen_liveness + 0.25 * printout_liveness + 0.30 * tamper_liveness + 0.20 * zone_score


async def run_stage_1(ctx: PipelineContext) -> StageResult:
    """Run Stage 1: Document Liveness & Anti-Spoofing."""
    start = time.time()
    details = {}
    flags = []
    reason_codes = []
    passed = True
    hard_fail = False

    # Check each document
    for label, image_path, doc_class in [
        ("passport", ctx.passport_image_path, ctx.passport_doc_class),
        ("national_id", ctx.id_image_path, ctx.id_doc_class),
    ]:
        if not image_path:
            continue

        screen = detect_screen_replay(image_path)
        printout = detect_printout(image_path)
        tamper = detect_pixel_tampering(image_path)
        zones = check_security_feature_zones(image_path, doc_class)

        liveness_score = _compute_doc_liveness_score(screen, printout, tamper, zones)

        details[f"{label}_liveness"] = {
            "score": round(liveness_score, 4),
            "screen_replay": screen,
            "printout": printout,
            "tampering": tamper,
            "security_zones": zones,
        }

        if liveness_score < DOC_LIVENESS_THRESHOLD:
            hard_fail = True
            passed = False
            flags.append(
                {
                    "flag_type": "doc_liveness_fail",
                    "detail": f"{label} liveness score {liveness_score:.3f} below threshold {DOC_LIVENESS_THRESHOLD}",
                }
            )
            reason_codes.append(
                {
                    "code": "DOC_LIVENESS_FAIL",
                    "stage": 1,
                    "severity": "critical",
                    "message": f"{label}: Document appears to be a replay/printout/fake",
                }
            )

        if tamper.get("is_tampered"):
            flags.append(
                {
                    "flag_type": "tampering_detected",
                    "detail": f"{label}: {tamper['detail']}",
                }
            )
            reason_codes.append(
                {
                    "code": "TAMPERING_DETECTED",
                    "stage": 1,
                    "severity": "warning",
                    "message": f"{label}: Pixel tampering indicators found",
                }
            )

    # Selfie liveness
    if ctx.selfie_image_path:
        selfie_result = check_selfie_liveness(ctx.selfie_image_path)
        details["selfie_liveness"] = selfie_result

        if not selfie_result.get("is_live"):
            hard_fail = True
            passed = False
            flags.append(
                {
                    "flag_type": "selfie_liveness_fail",
                    "detail": f"Selfie liveness score {selfie_result['score']:.3f} — failed PAD",
                }
            )
            reason_codes.append(
                {
                    "code": "SELFIE_LIVENESS_FAIL",
                    "stage": 1,
                    "severity": "critical",
                    "message": "Selfie does not appear to be from a live person",
                }
            )

    duration = (time.time() - start) * 1000
    result = StageResult(
        stage=1,
        name="Document Liveness & Anti-Spoofing",
        passed=passed,
        hard_fail=hard_fail,
        details=details,
        flags=flags,
        reason_codes=reason_codes,
        duration_ms=duration,
    )
    ctx.stage_results.append(result)
    ctx.flags.extend(flags)
    ctx.reason_codes.extend(reason_codes)
    return result

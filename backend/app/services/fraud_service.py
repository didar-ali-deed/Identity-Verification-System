import io
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import structlog
from PIL import Image
from PIL.ExifTags import TAGS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.document import Document

settings = get_settings()
logger = structlog.get_logger()


@dataclass
class FraudCheck:
    name: str
    score: float  # 0.0 (clean) to 1.0 (fraudulent)
    weight: float
    details: str
    passed: bool


@dataclass
class FraudResult:
    overall_score: float
    is_flagged: bool
    checks: list[FraudCheck] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_score": round(self.overall_score, 4),
            "is_flagged": self.is_flagged,
            "threshold": settings.fraud_score_threshold,
            "checks": [
                {
                    "name": c.name,
                    "score": round(c.score, 4),
                    "weight": c.weight,
                    "details": c.details,
                    "passed": c.passed,
                }
                for c in self.checks
            ],
        }


class FraudServiceError(Exception):
    def __init__(self, detail: str):
        self.detail = detail


async def analyze_document(
    image_path: str,
    ocr_data: dict | None = None,
    db: AsyncSession | None = None,
) -> FraudResult:
    """Run the full fraud detection pipeline on a document image.

    Returns FraudResult with overall score and individual check results.
    """
    if not Path(image_path).exists():
        raise FraudServiceError("Image file not found")

    checks: list[FraudCheck] = []

    # 1. Metadata analysis
    checks.append(check_metadata(image_path))

    # 2. Edge consistency
    checks.append(check_edges(image_path))

    # 3. Compression artifacts (ELA)
    checks.append(check_compression(image_path))

    # 4. Noise analysis
    checks.append(check_noise_consistency(image_path))

    # 5. Expiry validation
    if ocr_data:
        checks.append(check_expiry(ocr_data))

    # 6. Duplicate check
    if db and ocr_data:
        dup_check = await check_duplicate(db, ocr_data)
        checks.append(dup_check)

    # Calculate weighted score
    total_weight = sum(c.weight for c in checks)
    overall_score = sum(c.score * c.weight for c in checks) / total_weight if total_weight > 0 else 0.0

    is_flagged = overall_score >= settings.fraud_score_threshold

    result = FraudResult(
        overall_score=overall_score,
        is_flagged=is_flagged,
        checks=checks,
    )

    await logger.ainfo(
        "Fraud analysis complete",
        score=round(overall_score, 4),
        flagged=is_flagged,
        checks_run=len(checks),
    )

    return result


def check_metadata(image_path: str) -> FraudCheck:
    """Analyze image EXIF metadata for tampering indicators.

    Checks: software tags (Photoshop, GIMP), inconsistent dates,
    missing expected metadata.
    """
    score = 0.0
    issues = []

    try:
        img = Image.open(image_path)
        exif_data = img.getexif()

        if not exif_data:
            # No EXIF could mean stripped (common for real scans) or manipulated
            issues.append("No EXIF metadata found")
            score = 0.3
        else:
            # Check for editing software
            suspicious_software = [
                "photoshop",
                "gimp",
                "paint",
                "editor",
                "pixlr",
                "canva",
                "affinity",
                "lightroom",
            ]
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, str(tag_id)).lower()
                str_value = str(value).lower()

                if tag_name in ("software", "processingprogramname"):
                    for sw in suspicious_software:
                        if sw in str_value:
                            issues.append(f"Editing software detected: {value}")
                            score = max(score, 0.8)
                            break

                # Check for suspiciously recent creation dates
                if tag_name in ("datetime", "datetimeoriginal"):
                    try:
                        dt = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                        if (datetime.now() - dt).days < 1:
                            issues.append("Image created very recently")
                            score = max(score, 0.4)
                    except (ValueError, TypeError):
                        pass

    except Exception as e:
        issues.append(f"Metadata analysis error: {str(e)[:50]}")
        score = 0.2

    details = "; ".join(issues) if issues else "Metadata appears normal"
    return FraudCheck(
        name="metadata_analysis",
        score=score,
        weight=0.15,
        details=details,
        passed=score < 0.5,
    )


def check_edges(image_path: str) -> FraudCheck:
    """Analyze edge patterns for cut/paste artifacts.

    Uses Canny edge detection to find unnatural edge concentrations
    that may indicate document manipulation.
    """
    score = 0.0
    issues = []

    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return FraudCheck("edge_analysis", 0.2, 0.20, "Failed to read image", False)

        h, w = img.shape

        # Apply Canny edge detection
        edges = cv2.Canny(img, 50, 150)

        # Divide image into a grid and analyze edge distribution
        grid_rows, grid_cols = 4, 4
        cell_h, cell_w = h // grid_rows, w // grid_cols
        edge_densities = []

        for r in range(grid_rows):
            for c in range(grid_cols):
                cell = edges[r * cell_h : (r + 1) * cell_h, c * cell_w : (c + 1) * cell_w]
                density = np.sum(cell > 0) / cell.size
                edge_densities.append(density)

        edge_densities = np.array(edge_densities)
        mean_density = float(np.mean(edge_densities))
        std_density = float(np.std(edge_densities))

        # High variance in edge density can indicate spliced regions
        if std_density > 0.15:
            issues.append(f"High edge density variance ({std_density:.3f})")
            score = max(score, 0.6)

        # Very low edge density might mean a synthetic/blank document
        if mean_density < 0.01:
            issues.append("Suspiciously low edge density")
            score = max(score, 0.5)

        # Check for sharp rectangular edges (copy-paste boundaries)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rect_count = 0
        for contour in contours:
            approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
            area = cv2.contourArea(contour)
            if len(approx) == 4 and area > (h * w * 0.01):
                rect_count += 1

        if rect_count > 5:
            issues.append(f"Multiple rectangular edge patterns detected ({rect_count})")
            score = max(score, 0.5)

    except Exception as e:
        issues.append(f"Edge analysis error: {str(e)[:50]}")
        score = 0.2

    details = "; ".join(issues) if issues else "Edge patterns appear normal"
    return FraudCheck(
        name="edge_analysis",
        score=score,
        weight=0.20,
        details=details,
        passed=score < 0.5,
    )


def check_compression(image_path: str) -> FraudCheck:
    """Error Level Analysis (ELA) to detect edited regions.

    Resaves the image at a known quality and compares error levels.
    Edited regions show different compression artifacts.
    """
    score = 0.0
    issues = []

    try:
        original = Image.open(image_path).convert("RGB")

        # Resave at known JPEG quality
        buffer = io.BytesIO()
        original.save(buffer, "JPEG", quality=90)
        buffer.seek(0)
        resaved = Image.open(buffer)

        # Calculate pixel-level differences
        orig_arr = np.array(original, dtype=np.float32)
        resaved_arr = np.array(resaved, dtype=np.float32)
        diff = np.abs(orig_arr - resaved_arr)

        # Analyze the error levels
        _mean_error = float(np.mean(diff))  # noqa: F841
        _max_error = float(np.max(diff))  # noqa: F841
        std_error = float(np.std(diff))

        # High standard deviation in error levels indicates potential manipulation
        if std_error > 15:
            issues.append(f"High ELA variance (std={std_error:.1f})")
            score = max(score, 0.7)
        elif std_error > 10:
            issues.append(f"Moderate ELA variance (std={std_error:.1f})")
            score = max(score, 0.4)

        # Check for regions with significantly different error levels
        # (block-level analysis)
        h, w = diff.shape[:2]
        block_size = max(h, w) // 8
        if block_size > 0:
            block_errors = []
            for r in range(0, h - block_size, block_size):
                for c in range(0, w - block_size, block_size):
                    block = diff[r : r + block_size, c : c + block_size]
                    block_errors.append(float(np.mean(block)))

            if block_errors:
                block_std = float(np.std(block_errors))
                if block_std > 8:
                    issues.append(f"Inconsistent compression across regions (std={block_std:.1f})")
                    score = max(score, 0.6)

    except Exception as e:
        issues.append(f"Compression analysis error: {str(e)[:50]}")
        score = 0.2

    details = "; ".join(issues) if issues else "Compression artifacts appear consistent"
    return FraudCheck(
        name="compression_analysis",
        score=score,
        weight=0.15,
        details=details,
        passed=score < 0.5,
    )


def check_noise_consistency(image_path: str) -> FraudCheck:
    """Analyze noise patterns for consistency.

    Different image sources have different noise profiles.
    Spliced images may have inconsistent noise.
    """
    score = 0.0
    issues = []

    try:
        img = cv2.imread(image_path)
        if img is None:
            return FraudCheck("noise_analysis", 0.2, 0.10, "Failed to read image", False)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Estimate noise using Laplacian variance in different regions
        quad_h, quad_w = h // 2, w // 2
        quadrants = [
            gray[:quad_h, :quad_w],
            gray[:quad_h, quad_w:],
            gray[quad_h:, :quad_w],
            gray[quad_h:, quad_w:],
        ]

        noise_levels = []
        for q in quadrants:
            laplacian = cv2.Laplacian(q, cv2.CV_64F)
            noise_levels.append(float(laplacian.var()))

        noise_levels = np.array(noise_levels)
        noise_std = float(np.std(noise_levels))
        noise_mean = float(np.mean(noise_levels))

        # High variance between quadrants suggests manipulation
        if noise_mean > 0 and noise_std / noise_mean > 0.5:
            issues.append("Inconsistent noise levels across image regions")
            score = max(score, 0.6)

    except Exception as e:
        issues.append(f"Noise analysis error: {str(e)[:50]}")
        score = 0.2

    details = "; ".join(issues) if issues else "Noise patterns appear consistent"
    return FraudCheck(
        name="noise_analysis",
        score=score,
        weight=0.10,
        details=details,
        passed=score < 0.5,
    )


def check_expiry(ocr_data: dict) -> FraudCheck:
    """Validate document expiry date from OCR data."""
    score = 0.0
    issues = []

    expiry_str = ocr_data.get("expiry_date")
    if not expiry_str:
        return FraudCheck(
            name="expiry_validation",
            score=0.3,
            weight=0.10,
            details="Expiry date not detected in document",
            passed=True,
        )

    try:
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
        expiry_date = None
        for fmt in formats:
            try:
                expiry_date = datetime.strptime(str(expiry_str).strip(), fmt)
                break
            except ValueError:
                continue

        if not expiry_date:
            issues.append(f"Could not parse expiry date: {expiry_str}")
            score = 0.3
        elif expiry_date < datetime.now():
            days_expired = (datetime.now() - expiry_date).days
            issues.append(f"Document expired {days_expired} days ago")
            score = 0.9
        else:
            issues.append("Document is within validity period")
            score = 0.0

    except Exception:
        issues.append("Expiry date validation failed")
        score = 0.3

    details = "; ".join(issues)
    return FraudCheck(
        name="expiry_validation",
        score=score,
        weight=0.10,
        details=details,
        passed=score < 0.5,
    )


async def check_duplicate(db: AsyncSession, ocr_data: dict) -> FraudCheck:
    """Check if the same document number has been submitted before."""
    score = 0.0
    issues = []

    doc_number = ocr_data.get("document_number") or ocr_data.get("id_number") or ocr_data.get("license_number")

    if not doc_number:
        return FraudCheck(
            name="duplicate_check",
            score=0.0,
            weight=0.20,
            details="Document number not available for duplicate check",
            passed=True,
        )

    try:
        # Search for documents with matching document numbers in OCR data
        result = await db.execute(
            select(Document).where(
                Document.ocr_data.isnot(None),
            )
        )
        existing_docs = result.scalars().all()

        duplicate_count = 0
        for doc in existing_docs:
            if not doc.ocr_data:
                continue
            existing_number = (
                doc.ocr_data.get("document_number")
                or doc.ocr_data.get("id_number")
                or doc.ocr_data.get("license_number")
            )
            if existing_number and existing_number == doc_number:
                duplicate_count += 1

        if duplicate_count > 0:
            issues.append(f"Document number found in {duplicate_count} previous submission(s)")
            score = 0.9
        else:
            issues.append("No duplicate document number found")
            score = 0.0

    except Exception as e:
        issues.append(f"Duplicate check error: {str(e)[:50]}")
        score = 0.1

    details = "; ".join(issues)
    return FraudCheck(
        name="duplicate_check",
        score=score,
        weight=0.20,
        details=details,
        passed=score < 0.5,
    )

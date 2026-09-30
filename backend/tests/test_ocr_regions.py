import cv2
import numpy as np
import pytest

from app.services.ocr_service import _load_ocr_image


@pytest.mark.parametrize("label", ["Father / Husband Name", "Father's Name", "Father Name"])
def test_passport_father_label_cannot_be_used_as_gender_value(label):
    from app.services.ocr_service import parse_passport

    def row(text, y):
        return {"text": text, "bbox": [[10, y], [250, y], [250, y + 20], [10, y + 20]]}

    rows = [row("Sex", 0), row("M", 24), row(label, 48), row("JAMIE SAMPLE", 72)]
    result = parse_passport("\n".join(r["text"] for r in rows), rows, use_mrz=False)
    assert result["father_name"] == "JAMIE SAMPLE"
    assert result["gender"] == "Male"


def test_sideways_document_is_oriented_without_modifying_original(tmp_path):
    upright = np.full((200, 400, 3), 255, dtype=np.uint8)
    upright[20:60, 20:60] = 0
    sideways = cv2.rotate(upright, cv2.ROTATE_90_CLOCKWISE)
    path = tmp_path / "synthetic-sideways.png"
    cv2.imwrite(str(path), sideways)
    prepared = _load_ocr_image(str(path))
    assert np.array_equal(prepared, upright)
    assert np.array_equal(cv2.imread(str(path)), sideways)

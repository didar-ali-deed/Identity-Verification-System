import cv2
import numpy as np

from app.services.ocr_service import _load_ocr_image


def test_sideways_document_is_oriented_without_modifying_original(tmp_path):
    upright = np.full((200, 400, 3), 255, dtype=np.uint8)
    upright[20:60, 20:60] = 0
    sideways = cv2.rotate(upright, cv2.ROTATE_90_CLOCKWISE)
    path = tmp_path / "synthetic-sideways.png"
    cv2.imwrite(str(path), sideways)
    prepared = _load_ocr_image(str(path))
    assert np.array_equal(prepared, upright)
    assert np.array_equal(cv2.imread(str(path)), sideways)

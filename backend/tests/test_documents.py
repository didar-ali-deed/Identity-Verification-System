import pytest

from app.utils.validators import ValidationError, validate_uploaded_image


def test_valid_jpeg(valid_jpeg_bytes: bytes):
    mime, w, h = validate_uploaded_image(valid_jpeg_bytes)
    assert mime == "image/jpeg"
    assert w == 400
    assert h == 400


def test_valid_png(valid_png_bytes: bytes):
    mime, w, h = validate_uploaded_image(valid_png_bytes)
    assert mime == "image/png"
    assert w == 400
    assert h == 400


def test_small_image_rejected(small_image_bytes: bytes):
    with pytest.raises(ValidationError, match="too small"):
        validate_uploaded_image(small_image_bytes)


def test_invalid_file_type():
    with pytest.raises(ValidationError, match="Invalid file type"):
        validate_uploaded_image(b"x" * 2048)


def test_tiny_file():
    with pytest.raises(ValidationError, match="too small"):
        validate_uploaded_image(b"tiny")


def test_empty_file():
    with pytest.raises(ValidationError, match="too small"):
        validate_uploaded_image(b"")

import io

from PIL import Image

from app.config import get_settings

settings = get_settings()

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}

# Magic byte signatures for image validation
MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}

MIN_IMAGE_DIMENSION = 200
MAX_IMAGE_DIMENSION = 8000


class ValidationError(Exception):
    def __init__(self, detail: str):
        self.detail = detail


def validate_file_magic_bytes(file_content: bytes) -> str:
    """Validate file type via magic bytes. Returns detected MIME type."""
    for magic, mime_type in MAGIC_BYTES.items():
        if file_content[: len(magic)] == magic:
            return mime_type
    raise ValidationError("Invalid file type. Only JPEG and PNG images are allowed")


def validate_file_size(file_content: bytes) -> None:
    """Validate file does not exceed max size."""
    if len(file_content) > settings.max_file_size_bytes:
        raise ValidationError(f"File size exceeds maximum of {settings.max_file_size_mb}MB")
    if len(file_content) < 1024:
        raise ValidationError("File is too small to be a valid image")


def validate_image_dimensions(file_content: bytes) -> tuple[int, int]:
    """Validate image dimensions. Returns (width, height)."""
    try:
        image = Image.open(io.BytesIO(file_content))
        width, height = image.size
    except Exception as e:
        raise ValidationError("Cannot read image. File may be corrupted") from e

    if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
        raise ValidationError(f"Image too small. Minimum dimensions: {MIN_IMAGE_DIMENSION}x{MIN_IMAGE_DIMENSION}px")
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ValidationError(f"Image too large. Maximum dimensions: {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}px")

    return width, height


def validate_image_integrity(file_content: bytes) -> None:
    """Verify the image can be fully decoded (not truncated)."""
    try:
        image = Image.open(io.BytesIO(file_content))
        image.verify()
    except Exception as e:
        raise ValidationError("Image file is corrupted or truncated") from e


def strip_image_metadata(file_content: bytes, mime_type: str) -> bytes:
    """Re-encode image to strip EXIF and other metadata."""
    image = Image.open(io.BytesIO(file_content))
    # Create new image without metadata
    clean = Image.new(image.mode, image.size)
    clean.putdata(list(image.getdata()))
    buf = io.BytesIO()
    fmt = "JPEG" if mime_type == "image/jpeg" else "PNG"
    clean.save(buf, format=fmt, quality=95 if fmt == "JPEG" else None)
    return buf.getvalue()


def sanitize_text_input(text: str) -> str:
    """Sanitize user text input to prevent XSS and injection."""
    import html

    text = text.strip()
    text = html.escape(text)
    # Remove null bytes
    text = text.replace("\x00", "")
    return text


def validate_uploaded_image(file_content: bytes) -> tuple[str, int, int]:
    """Run all validations on an uploaded image.

    Returns (mime_type, width, height).
    """
    validate_file_size(file_content)
    mime_type = validate_file_magic_bytes(file_content)
    validate_image_integrity(file_content)
    width, height = validate_image_dimensions(file_content)
    return mime_type, width, height

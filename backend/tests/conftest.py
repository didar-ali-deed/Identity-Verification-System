import asyncio
import io
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def valid_jpeg_bytes() -> bytes:
    """Generate a valid JPEG image for testing."""
    img = Image.new("RGB", (400, 400), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def valid_png_bytes() -> bytes:
    """Generate a valid PNG image for testing."""
    img = Image.new("RGB", (400, 400), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def small_image_bytes() -> bytes:
    """Generate an image too small for validation."""
    img = Image.new("RGB", (50, 50), color="green")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

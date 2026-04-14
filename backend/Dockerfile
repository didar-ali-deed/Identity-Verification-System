FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_TIMEOUT=300 \
    PIP_RETRIES=5 \
    PIP_DEFAULT_TIMEOUT=300

WORKDIR /app

# System deps for OpenCV + PaddleOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ── Layer 1a: PyTorch CUDA 12.1 wheel (works with CUDA 13.0 driver) ─────────
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cu121 \
    torch torchvision

# ── Layer 1b: heavy ML packages (slow, cached) ──────────────────────────────
COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt

# ── Layer 2: lightweight app packages (fast, ~2 min) ────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# NOTE: PaddleOCR models download automatically on first OCR call.
# They are NOT baked into the image — bcebos.com CDN is unreliable at build time.

COPY . .

RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

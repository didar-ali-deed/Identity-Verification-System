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

# ── Layer 1a: CPU PyTorch by default; set TORCH_INDEX_URL for a GPU build ────
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir \
    --index-url ${TORCH_INDEX_URL} \
    torch torchvision

# ── Layer 1b: heavy ML packages (slow, cached) ──────────────────────────────
COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt

# ── Layer 2: lightweight app packages (fast, ~2 min) ────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# TrOCR downloads its model on first OCR use into the mounted Hugging Face cache.

COPY . .

RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

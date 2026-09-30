FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_TIMEOUT=300 \
    PIP_RETRIES=5 \
    PIP_DEFAULT_TIMEOUT=300

WORKDIR /app

# System deps for OpenCV and inference libraries
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
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade "pip==26.2.1" && \
    pip install --resume-retries 10 -r requirements-ml.txt

# DeepFace requires legacy Keras when running with TensorFlow 2.16 or newer.
COPY requirements-tensorflow.txt .
RUN pip install --no-cache-dir -r requirements-tensorflow.txt

ARG INSTALL_ENHANCED=false
COPY requirements-enhanced.txt .
RUN if [ "$INSTALL_ENHANCED" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends build-essential && \
      pip install --no-cache-dir -r requirements-enhanced.txt && \
      rm -rf /var/lib/apt/lists/*; \
    fi

# ── Layer 2: lightweight app packages (fast, ~2 min) ────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY requirements-ocr.txt .
RUN pip install --no-cache-dir -r requirements-ocr.txt

# MediaPipe's image runtime requires EGL even for CPU inference.
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 libgles2 && rm -rf /var/lib/apt/lists/*

# EasyOCR downloads its models on first use into the mounted model cache.

COPY . .

RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

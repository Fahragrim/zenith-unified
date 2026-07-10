# ──────────────────────────────────────────────────────────────────────────────
# Dockerfile — Zenith Unified (multi-stage build)
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libusb-1.0-0-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY data/ ./data/

RUN pip install --upgrade pip && \
    pip install --no-cache-dir build && \
    python -m build --wheel

# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Zenith Unified" \
      org.opencontainers.image.description="AI-powered Android diagnostics, repair & recovery" \
      org.opencontainers.image.version="0.4.0" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    adb \
    fastboot \
    libusb-1.0-0 \
    usbutils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

COPY data/ ./data/

ENV ZENITH_DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["zenith"]
CMD ["--help"]

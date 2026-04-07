# syntax=docker/dockerfile:1.4
# Tsushin Backend Dockerfile
# Phase 9: Application Containerization
#
# Multi-stage build for FastAPI backend with PostgreSQL + ChromaDB

# ============================================================================
# Stage 1: Builder - Install dependencies
# ============================================================================
FROM python:3.11-slim AS builder

ARG INSTALL_OPTIONAL_DEPS=true

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
WORKDIR /build

# Copy requirements files
COPY requirements-base.txt requirements-app.txt requirements-optional.txt requirements-phase4.txt ./

# Install tiered dependencies with BuildKit cache mounts for fast iterative rebuilds
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements-base.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-app.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    if [ "$INSTALL_OPTIONAL_DEPS" = "true" ]; then \
        pip install -r requirements-optional.txt; \
    fi

# CPU-only torch wheel — skips ~4.3GB of NVIDIA/CUDA/triton binaries.
# Embeddings (sentence-transformers) run on CPU via asyncio.to_thread().
# Must be installed BEFORE requirements-phase4.txt so sentence-transformers
# finds the CPU torch wheel already satisfied.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url https://download.pytorch.org/whl/cpu torch

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-phase4.txt

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.11-slim AS runtime

# Phase 9.3: Architecture detection for multi-platform support
ARG TARGETARCH

# Optional-asset build flags (default true for backwards compatibility).
# Set to false at build time to produce lean images:
#   docker build --build-arg INSTALL_PLAYWRIGHT=false --build-arg INSTALL_FFMPEG=false ...
ARG INSTALL_PLAYWRIGHT=true
ARG INSTALL_FFMPEG=true

# Install core runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    sqlite3 \
    libpq5 \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Optional: ffmpeg (used by kokoro_tts_provider.py for WAV->Opus conversion)
RUN if [ "$INSTALL_FFMPEG" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends ffmpeg \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# Optional: Playwright Chromium system dependencies
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            libnss3 \
            libnspr4 \
            libatk1.0-0 \
            libatk-bridge2.0-0 \
            libcups2 \
            libdrm2 \
            libdbus-1-3 \
            libxkbcommon0 \
            libatspi2.0-0 \
            libxcomposite1 \
            libxdamage1 \
            libxfixes3 \
            libxrandr2 \
            libgbm1 \
            libpango-1.0-0 \
            libcairo2 \
            libasound2 \
        && rm -rf /var/lib/apt/lists/*; \
    fi


# Create non-root user for security
# Also create docker group with same GID as host for Docker socket access (GID 999)
RUN groupadd -g 1000 tsushin && \
    useradd -u 1000 -g tsushin -m -s /bin/bash tsushin && \
    groupadd -g 999 dockersock && \
    usermod -aG dockersock tsushin

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install Playwright browser (Chromium only for smaller image size)
# BUG-315 fix: Use shared path so non-root tsushin user can find browsers at runtime
# Gated by INSTALL_PLAYWRIGHT ARG — Chromium binary is ~1.1GB
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
        playwright install chromium && playwright install-deps chromium && \
        chmod -R 755 /opt/playwright-browsers; \
    fi

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=tsushin:tsushin . .

# Create required directories
RUN mkdir -p /app/data /app/data/chroma /app/data/backups /app/logs \
    /tmp/tsushin_images /tmp/tsushin_screenshots /tmp/tsushin_audio && \
    chown -R tsushin:tsushin /app/data /app/logs \
    /tmp/tsushin_images /tmp/tsushin_screenshots /tmp/tsushin_audio

# BUG-400 fix: Pre-download the sentence-transformer embedding model during
# image build so it is cached in the image layer.  Without this, the first KB
# document upload triggers a ~80 MB download at runtime which can OOM-crash
# memory-constrained containers.
# Run as root so the model cache directory (/root/.cache or site-packages) is
# writable; after USER switch the model files are already on the read-only
# image layer accessible to any user.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Switch to non-root user
USER tsushin

# Expose port
EXPOSE 8081

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
    CMD curl -f http://localhost:8081/api/health || exit 1

# Default environment variables (can be overridden)
ENV TSN_APP_HOST=0.0.0.0
ENV TSN_APP_PORT=8081
ENV TSN_LOG_LEVEL=INFO
ENV INTERNAL_DB_PATH=/app/data/agent.db
ENV TSN_CHROMA_DIR=/app/data/chroma
ENV TSN_WORKSPACE_DIR=/app/data/workspace
ENV TSN_BACKUPS_DIR=/app/data/backups
ENV TSN_LOG_FILE=/app/logs/tsushin.log

# Run the application
# 1 worker: all CPU-bound embedding calls use asyncio.to_thread() so they
# no longer block the event loop.  Single worker halves model memory.
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8081", "--workers", "1", "--timeout-keep-alive", "120"]

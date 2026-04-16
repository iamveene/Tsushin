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
# NOTE: mcr.microsoft.com/playwright/python:v1.48.0-jammy (Ubuntu 22.04) ships
# Python 3.10 only — incompatible with the Python 3.11 venv built above.
# Item 3 build-time saving is achieved instead via a BuildKit cache mount on the
# playwright install step below, which caches the ~1.1GB Chromium download
# between cold builds without requiring a base-image switch.
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

# v0.6.0 Remote Access: install cloudflared binary so the backend can manage
# a Cloudflare Tunnel subprocess. Pinned to a specific upstream release with
# SHA256 verification (supply-chain hardening — do NOT switch back to
# releases/latest). Bump CLOUDFLARED_VERSION + checksums to upgrade.
# Installed while still root so /usr/local/bin/cloudflared has the correct
# permissions; the non-root `tsushin` user only needs execute access.
ARG CLOUDFLARED_VERSION=2026.3.0
ARG CLOUDFLARED_SHA256_AMD64=4a9e50e6d6d798e90fcd01933151a90bf7edd99a0a55c28ad18f2e16263a5c30
ARG CLOUDFLARED_SHA256_ARM64=0755ba4cbab59980e6148367fcf53a8f3ec85a97deefd63c2420cf7850769bee
RUN set -eux; \
    arch="$(uname -m)"; \
    case "$arch" in \
      x86_64) cf_arch="amd64"; cf_sha="${CLOUDFLARED_SHA256_AMD64}" ;; \
      aarch64|arm64) cf_arch="arm64"; cf_sha="${CLOUDFLARED_SHA256_ARM64}" ;; \
      *) echo "Unsupported architecture for cloudflared: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-linux-${cf_arch}" -o /usr/local/bin/cloudflared; \
    echo "${cf_sha}  /usr/local/bin/cloudflared" | sha256sum -c -; \
    chmod 0755 /usr/local/bin/cloudflared; \
    /usr/local/bin/cloudflared --version

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
# Use rename-if-taken logic: Ubuntu Jammy base image pre-creates UID/GID 1000 as 'ubuntu'.
RUN set -eux; \
    # GID 1000: rename existing group to 'tsushin' or create fresh
    if getent group 1000 >/dev/null 2>&1; then \
        EXISTING_GRP=$(getent group 1000 | cut -d: -f1); \
        [ "$EXISTING_GRP" = "tsushin" ] || groupmod -n tsushin "$EXISTING_GRP"; \
    else \
        groupadd -g 1000 tsushin; \
    fi; \
    # UID 1000: rename existing user to 'tsushin' or create fresh
    if getent passwd 1000 >/dev/null 2>&1; then \
        EXISTING_USR=$(getent passwd 1000 | cut -d: -f1); \
        if [ "$EXISTING_USR" != "tsushin" ]; then \
            usermod -l tsushin -d /home/tsushin -m "$EXISTING_USR"; \
        fi; \
    else \
        useradd -u 1000 -g tsushin -m -s /bin/bash tsushin; \
    fi; \
    chsh -s /bin/bash tsushin 2>/dev/null || true; \
    # GID 999: rename existing group to 'dockersock' or create fresh
    if getent group 999 >/dev/null 2>&1; then \
        EXISTING_GRP=$(getent group 999 | cut -d: -f1); \
        [ "$EXISTING_GRP" = "dockersock" ] || groupmod -n dockersock "$EXISTING_GRP"; \
    else \
        groupadd -g 999 dockersock; \
    fi; \
    usermod -aG dockersock tsushin

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install Playwright browser (Chromium only for smaller image size)
# BUG-315 fix: Use shared path so non-root tsushin user can find browsers at runtime
# Item 3 build perf: BuildKit cache mount on /opt/pw-cache avoids re-downloading
# the ~1.1GB Chromium binary on every cold rebuild — only a fast local copy occurs
# on warm builds. Gated by INSTALL_PLAYWRIGHT ARG.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
RUN --mount=type=cache,target=/opt/pw-cache \
    if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
        PLAYWRIGHT_BROWSERS_PATH=/opt/pw-cache playwright install chromium && \
        playwright install-deps chromium && \
        mkdir -p /opt/playwright-browsers && \
        cp -r /opt/pw-cache/. /opt/playwright-browsers/ && \
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
# image build into a shared cache directory accessible to the non-root user.
# Without this, the first KB upload triggers a ~80MB runtime download that
# can OOM-crash memory-constrained containers.
ENV SENTENCE_TRANSFORMERS_HOME=/app/.model_cache
RUN mkdir -p /app/.model_cache && \
    max_attempts=3 && \
    prewarm_ok=false && \
    for attempt in 1 2 3; do \
        echo "Prewarming all-MiniLM-L6-v2 (attempt ${attempt}/${max_attempts})"; \
        if python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"; then \
            echo "Embedding model prewarm completed."; \
            prewarm_ok=true; \
            break; \
        fi; \
        if [ "$attempt" -lt "$max_attempts" ]; then \
            sleep_time=$((attempt * 5)); \
            echo "Prewarm failed; retrying in ${sleep_time}s..."; \
            sleep "$sleep_time"; \
        fi; \
    done && \
    if [ "$prewarm_ok" != "true" ]; then \
        echo "WARNING: Embedding model prewarm skipped after retries; runtime will lazy-download if needed."; \
    fi && \
    chown -R tsushin:tsushin /app/.model_cache

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

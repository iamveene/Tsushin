# Tsushin Backend Dockerfile
# Phase 9: Application Containerization
#
# Multi-stage build for FastAPI backend with SQLite + ChromaDB

# ============================================================================
# Stage 1: Builder - Install dependencies
# ============================================================================
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
WORKDIR /build

# Copy requirements files
COPY requirements.txt requirements-phase4.txt ./

# Install main dependencies first (for layer caching)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install additional Phase 4 dependencies (semantic search)
RUN pip install --no-cache-dir -r requirements-phase4.txt

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.11-slim AS runtime

# Phase 9.3: Architecture detection for multi-platform support
ARG TARGETARCH

# Install runtime dependencies, security scanning tools, and Playwright system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    nmap \
    wget \
    unzip \
    whois \
    ffmpeg \
    # Playwright system dependencies for Chromium
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
    && rm -rf /var/lib/apt/lists/*

# Install Nuclei vulnerability scanner - architecture-aware
RUN ARCH=$([ "$TARGETARCH" = "arm64" ] && echo "arm64" || echo "amd64") && \
    echo "Installing nuclei for architecture: $ARCH" && \
    wget -q "https://github.com/projectdiscovery/nuclei/releases/download/v3.3.7/nuclei_3.3.7_linux_${ARCH}.zip" \
    && unzip -o "nuclei_3.3.7_linux_${ARCH}.zip" \
    && mv nuclei /usr/local/bin/ \
    && rm -f "nuclei_3.3.7_linux_${ARCH}.zip" LICENSE.md README*.md \
    && chmod +x /usr/local/bin/nuclei

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
# Must run as root before switching to non-root user
RUN playwright install chromium && \
    playwright install-deps chromium

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=tsushin:tsushin . .

# Create required directories
RUN mkdir -p /app/data /app/data/chroma /app/data/backups /app/logs && \
    chown -R tsushin:tsushin /app/data /app/logs

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
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8081"]

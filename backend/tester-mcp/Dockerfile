# Tester WhatsApp MCP Dockerfile
# Phase 9: Application Containerization
#
# Multi-stage build for WhatsApp Tester MCP instance
# Used for QA testing and agent validation

# ============================================================================
# Stage 1: Build the Go binary
# ============================================================================
FROM golang:1.24-alpine AS builder

# Install build dependencies (including gcc for CGO)
RUN apk add --no-cache \
    git \
    ca-certificates \
    gcc \
    musl-dev \
    sqlite-dev

# Set working directory
WORKDIR /build

# Copy Go module files first (for layer caching)
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY main.go ./

# Build the binary (statically linked)
# CGO is needed for sqlite3
RUN CGO_ENABLED=1 go build -ldflags="-w -s -extldflags '-static'" -o whatsapp-bridge main.go

# ============================================================================
# Stage 2: Runtime container
# ============================================================================
FROM alpine:3.18

# Install runtime dependencies
RUN apk add --no-cache \
    ca-certificates \
    curl \
    sqlite \
    tzdata

# Create non-root user
RUN addgroup -g 1000 whatsapp && \
    adduser -D -u 1000 -G whatsapp whatsapp

# Copy binary from builder
COPY --from=builder /build/whatsapp-bridge /app/whatsapp-bridge
RUN chmod +x /app/whatsapp-bridge

# Create directories
RUN mkdir -p /app/store /app/logs && \
    chown -R whatsapp:whatsapp /app

# Set working directory
WORKDIR /app

# Switch to non-root user
USER whatsapp

# Expose internal port (always 8080 inside container)
EXPOSE 8080

# Health check - check if HTTP server is responding
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
  CMD curl -f http://localhost:8080/health || exit 1

# Labels for identification
LABEL org.opencontainers.image.title="Tester WhatsApp MCP"
LABEL org.opencontainers.image.description="WhatsApp MCP instance for QA testing and agent validation"
LABEL org.opencontainers.image.vendor="Tsushin"

# Set entrypoint
ENTRYPOINT ["/app/whatsapp-bridge"]

# Default arguments (can be overridden)
CMD ["--port", "8080"]

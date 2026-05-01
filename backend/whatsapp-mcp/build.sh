#!/bin/bash
# Build script for WhatsApp MCP Docker image
# Phase 8: Multi-Tenant MCP Containerization

set -e

IMAGE_NAME="${IMAGE_NAME:-tsushin/whatsapp-mcp}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE_REF="${TSN_WHATSAPP_MCP_IMAGE:-}"
if [ -z "${IMAGE_REF}" ]; then
    IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"
fi

echo "=========================================="
echo "Building WhatsApp MCP Docker Image"
echo "=========================================="
echo "Image: ${IMAGE_REF}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Build the image
echo "[BUILD] Building Docker image..."
docker build -t "${IMAGE_REF}" "${SCRIPT_DIR}"

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✓ Build successful!"
    echo "=========================================="
    echo "Image: ${IMAGE_REF}"
    echo ""
    echo "Next steps:"
    echo "  1. Test the image:"
    echo "     docker run --rm -p 8080:8080 ${IMAGE_REF}"
    echo ""
    echo "  2. Create MCP instance via API:"
    echo "     POST /api/mcp/instances"
else
    echo ""
    echo "=========================================="
    echo "✗ Build failed!"
    echo "=========================================="
    exit 1
fi

#!/bin/bash
# Build script for WhatsApp MCP Docker image
# Phase 8: Multi-Tenant MCP Containerization

set -e

IMAGE_NAME="tsushin/whatsapp-mcp"
IMAGE_TAG="latest"

echo "=========================================="
echo "Building WhatsApp MCP Docker Image"
echo "=========================================="
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Build the image
echo "[BUILD] Building Docker image..."
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" "${SCRIPT_DIR}"

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✓ Build successful!"
    echo "=========================================="
    echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
    echo ""
    echo "Next steps:"
    echo "  1. Test the image:"
    echo "     docker run --rm -p 8080:8080 ${IMAGE_NAME}:${IMAGE_TAG}"
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

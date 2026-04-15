# Tester WhatsApp MCP

A standalone or legacy WhatsApp MCP surface dedicated to QA testing and agent validation.

## Overview

The Tester WhatsApp MCP provides an isolated WhatsApp bridge for:
- End-to-end testing of agent responses
- Automated QA flows validation
- Message inspection and verification
- Agent function testing

The current repository root compose stack does **not** define a `tester-mcp` service or a `testing` profile. In current Tsushin builds, Hub tester controls prefer a legacy standalone `tester-mcp` container when present and otherwise target the tenant's active runtime tester instance.

## Standalone Usage

```bash
# Build from the repository root
docker build -t tsushin/tester-mcp:latest backend/tester-mcp

# Run
docker run -d \
  --name tester-mcp \
  -p 8088:8080 \
  -e MCP_API_SECRET=change-me \
  -v "$(pwd)/backend/tester-mcp/store:/app/store" \
  tsushin/tester-mcp:latest \
  --port 8080
```

## Configuration

| Setting | Type | Description | Default |
|--------|------|-------------|---------|
| `--port` | CLI flag | REST API port exposed by the Go service inside the container | `8080` |
| `MCP_API_SECRET` | Environment variable | Optional Bearer token that protects API endpoints when set | unset |

## API Endpoints

- `GET /api/health` - Health check
- `POST /api/send` - Send message
- `POST /api/download` - Download media
- `GET /api/qr-code` - Get QR code for authentication

If `MCP_API_SECRET` is set, protected endpoints require `Authorization: Bearer <token>`.

## QA Integration

When enabled in the Hub configuration, this surface can be used for:
1. Sending test messages to agents
2. Verifying agent responses
3. Testing scheduled conversations
4. Validating multi-step flows

## Directory Structure

```
tester-mcp/
├── Dockerfile      # Multi-stage build
├── main.go         # Go source (WhatsApp bridge)
├── go.mod          # Go module definition
├── go.sum          # Go dependencies
└── README.md       # This file
```

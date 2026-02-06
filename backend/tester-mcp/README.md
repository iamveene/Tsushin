# Tester WhatsApp MCP

**Phase 9: Application Containerization**

A containerized WhatsApp MCP instance dedicated for QA testing and agent validation.

## Overview

The Tester WhatsApp MCP provides an isolated WhatsApp bridge for:
- End-to-end testing of agent responses
- Automated QA flows validation
- Message inspection and verification
- Agent function testing

## Usage

### With Docker Compose (Recommended)

```bash
# Start with testing profile
docker compose --profile testing up -d

# View logs
docker compose logs -f tester-mcp
```

### Standalone

```bash
# Build
docker build -t tsushin/tester-mcp:latest .

# Run
docker run -d \
  --name tester-mcp \
  -p 8088:8080 \
  -v ./store:/app/store \
  tsushin/tester-mcp:latest
```

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `PHONE_NUMBER` | WhatsApp phone number for tester | - |
| `PORT` | Internal port (container) | 8080 |

## API Endpoints

- `GET /health` - Health check
- `POST /api/send` - Send message
- `POST /api/download` - Download media
- `GET /api/qr-code` - Get QR code for authentication

## QA Integration

When enabled in the Hub configuration, this MCP instance can be used for:
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

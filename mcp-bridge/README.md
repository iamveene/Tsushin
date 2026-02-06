# MCP HTTP Bridge

HTTP bridge for MCP (Model Context Protocol) tool execution from Docker containers.

## Overview

This server runs on your host machine and provides an HTTP interface for the Docker-based Tsushin backend to execute MCP browser automation tools.

```
┌──────────────────┐      HTTP/REST      ┌───────────────────┐      MCP/stdio      ┌──────────────────┐
│  Tsushin Backend │  -----------------> │  MCP HTTP Bridge  │ ------------------> │ Browser MCP      │
│  (Docker)        │                     │  (This Server)    │                     │ (Host Browser)   │
└──────────────────┘                     └───────────────────┘                     └──────────────────┘
```

## Installation

```bash
cd mcp-bridge
pip install -r requirements.txt
```

## Usage

### Start the bridge server:

```bash
python server.py
```

### With custom port:

```bash
python server.py --port 8765
```

### With API key authentication:

```bash
export MCP_BRIDGE_API_KEY="your-secure-key"
python server.py
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_BRIDGE_PORT` | 8765 | HTTP port to listen on |
| `MCP_BRIDGE_API_KEY` | (none) | Optional API key for authentication |

### Docker Integration

The backend container needs to be able to reach the bridge server. In Docker Compose, use `host.docker.internal`:

```yaml
services:
  backend:
    environment:
      - MCP_BRIDGE_URL=http://host.docker.internal:8765
      - MCP_BRIDGE_API_KEY=your-secure-key
```

## API Endpoints

### Health Check

```bash
GET /health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T12:00:00Z",
  "active_sessions": 2,
  "tools_available": 15
}
```

### Execute MCP Tool

```bash
POST /mcp/call
Content-Type: application/json
Authorization: Bearer your-api-key

{
  "tool": "browser_navigate",
  "params": {"url": "https://example.com"},
  "session_id": "abc123",
  "mcp_backend": "playwright"
}
```

Response:
```json
{
  "success": true,
  "result": {
    "url": "https://example.com",
    "title": "Example Domain"
  },
  "duration_ms": 150
}
```

### End Session

```bash
POST /mcp/session/end
Content-Type: application/json
Authorization: Bearer your-api-key

{
  "session_id": "abc123"
}
```

### Get Request Logs

```bash
GET /logs?limit=100
Authorization: Bearer your-api-key
```

## Security

- **API Key Authentication**: Optional but recommended for production
- **Tool Whitelist**: Only browser-related MCP tools are allowed
- **Rate Limiting**: 60 requests per minute per session
- **Request Logging**: All requests are logged for audit

## Allowed MCP Tools

### Playwright MCP
- `browser_navigate`
- `browser_click`
- `browser_type`
- `browser_snapshot`
- `browser_take_screenshot`
- `browser_evaluate`
- `browser_close`
- `browser_fill_form`
- `browser_press_key`

### Claude in Chrome
- `navigate`
- `computer`
- `read_page`
- `find`
- `form_input`
- `javascript_tool`
- `get_page_text`

## Development

### Running Tests

```bash
pytest tests/
```

### Mock Mode

The current implementation includes mock responses for testing.
To use real MCP tools, implement the `_execute_mcp_tool` method
to connect to your MCP server.

## Troubleshooting

### Bridge not reachable from Docker

1. Ensure the bridge is running on port 8765
2. Check firewall settings
3. Verify `host.docker.internal` resolves correctly

### Authentication errors

1. Ensure `MCP_BRIDGE_API_KEY` matches on both sides
2. Check the `Authorization` header format

### Rate limiting

If you're hitting rate limits, the response will include:
```json
{
  "success": false,
  "error": "Rate limit exceeded",
  "remaining": 0
}
```

Wait a minute or adjust `MAX_REQUESTS_PER_MINUTE` in the server.

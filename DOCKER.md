# Tsushin Docker Deployment Guide

**Phase 9: Application Containerization**

This guide covers deploying Tsushin using Docker containers.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   backend   │  │  frontend   │  │  tester-mcp         │  │
│  │  FastAPI    │  │  Next.js    │  │  (QA Profile)       │  │
│  │  Port 8081  │  │  Port 3030  │  │  Port 8088          │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                     │             │
│         ▼                ▼                     ▼             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Persistent Volumes                       │   │
│  │  ./backend/data → SQLite + ChromaDB + MCP data       │   │
│  │  ./logs → Application logs                            │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Docker Engine 20.10+
- Docker Compose V2 (or docker-compose-plugin)
- At least 4GB RAM available
- API keys for AI providers (Gemini, OpenAI, etc.)

## Quick Start

### 1. Clone and Configure

```bash
cd /opt/tsushin

# Copy environment template
cp env.example .env

# Edit .env with your API keys
nano .env
```

### 2. Required Environment Variables

At minimum, configure these in your `.env`:

```bash
# AI Provider (at least one required)
GEMINI_API_KEY=your-gemini-api-key

# Security (generate a secure key)
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

### 3. Start Services

```bash
# Build and start all services
docker compose up -d --build

# View logs
docker compose logs -f
```

### 4. Access the Application

- **Frontend**: http://localhost:3030
- **Backend API**: http://localhost:8081
- **Health Check**: http://localhost:8081/api/health

## Service Details

### Backend (tsushin-backend)

FastAPI application with:
- SQLite database
- ChromaDB vector store
- Scheduler worker
- WebSocket support

**Volumes:**
- `./backend/data` → `/app/data` (database, vectors, workspace)
- `./logs/backend` → `/app/logs` (application logs)

### Frontend (tsushin-frontend)

Next.js 14 application with:
- Server-side rendering
- Standalone output mode

**Build Args:**
- `NEXT_PUBLIC_API_URL` - Backend API URL (default: http://localhost:8081)

### Tester MCP (Optional)

WhatsApp bridge for QA testing. Activated with the `testing` profile:

```bash
# Start with tester MCP
docker compose --profile testing up -d
```

**Port:** 8088 (configurable via `TESTER_MCP_PORT`)

## Common Commands

### Starting Services

```bash
# Start all services (background)
docker compose up -d

# Start with rebuild
docker compose up -d --build

# Start specific service
docker compose up -d backend

# Start with testing profile
docker compose --profile testing up -d
```

### Stopping Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes (CAUTION: deletes data)
docker compose down -v

# Stop specific service
docker compose stop backend
```

### Viewing Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend

# Last 100 lines
docker compose logs --tail=100 backend
```

### Rebuilding

```bash
# Rebuild specific service
docker compose build backend

# Rebuild without cache
docker compose build --no-cache backend

# Rebuild and restart
docker compose up -d --build backend
```

### Health Checks

```bash
# Check backend health
curl http://localhost:8081/api/health

# Check container status
docker compose ps

# Check container health
docker inspect tsushin-backend --format='{{.State.Health.Status}}'
```

## Data Persistence

All data is stored in bind-mounted volumes:

| Host Path | Container Path | Description |
|-----------|----------------|-------------|
| `./backend/data/agent.db` | `/app/data/agent.db` | SQLite database |
| `./backend/data/chroma/` | `/app/data/chroma/` | Vector embeddings |
| `./backend/data/mcp/` | `/app/data/mcp/` | MCP instance data |
| `./logs/backend/` | `/app/logs/` | Application logs |

### Backup

```bash
# Backup database
cp backend/data/agent.db backups/agent.db.$(date +%Y%m%d)

# Full data backup
tar -czvf backups/tsushin-data-$(date +%Y%m%d).tar.gz backend/data/
```

## Network Configuration

### Host Access from Container

Use `host.docker.internal` to access host services:

```bash
# Access Ollama on host
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Access Kokoro TTS on host
KOKORO_SERVICE_URL=http://host.docker.internal:8880
```

### Custom Networks

By default, services use the `tsushin-network` bridge network. For custom configurations:

```yaml
# In docker-compose.yml
networks:
  tsushin-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose logs backend

# Check if port is in use
lsof -i :8081

# Remove and recreate
docker compose down
docker compose up -d --build
```

### Database Issues

```bash
# Enter container
docker exec -it tsushin-backend bash

# Check database
sqlite3 /app/data/agent.db ".tables"
```

### Memory Issues

If sentence-transformers model loading is slow:

```bash
# Increase Docker memory limit (Docker Desktop)
# Settings → Resources → Memory → 6GB+

# Or pre-download models
docker exec tsushin-backend python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

### Permission Issues

```bash
# Fix volume permissions
sudo chown -R 1000:1000 backend/data/
sudo chown -R 1000:1000 logs/
```

## Production Considerations

### Security

1. **Use secrets management** instead of `.env` files
2. **Enable HTTPS** with a reverse proxy (nginx/traefik)
3. **Restrict network access** to required ports only
4. **Generate strong JWT secret**:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

### Performance

1. **Use named volumes** for better I/O:
   ```yaml
   volumes:
     tsushin-data:
     tsushin-chroma:
   ```

2. **Configure resource limits**:
   ```yaml
   services:
     backend:
       deploy:
         resources:
           limits:
             memory: 4G
           reservations:
             memory: 2G
   ```

### Monitoring

1. **Health checks** are configured for all services
2. **Log aggregation** - Mount logs to central location
3. **Metrics** - Add Prometheus/Grafana for monitoring

## Version Information

- Backend: Python 3.11, FastAPI
- Frontend: Node 20, Next.js 14
- Tester MCP: Go 1.24, whatsmeow

# Tsushin Docker Deployment Guide

This guide covers deploying Tsushin using Docker containers.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐  ┌─────────────────────┐  │
│  │   backend   │  │  frontend   │  │ postgres │  │ tester surface       │  │
│  │  FastAPI    │  │  Next.js    │  │ PG 16    │  │ (legacy or runtime)  │  │
│  │  Port 8081  │  │  Port 3030  │  │ Port 5432│  │  Port 8088 when used │  │
│  └──────┬──────┘  └──────┬──────┘  └────┬─────┘  └──────────┬──────────┘  │
│         │                │               │                   │             │
│         ▼                ▼               ▼                   ▼             │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │              Persistent Volumes                                   │      │
│  │  ./backend/data → ChromaDB + MCP data                            │      │
│  │  tsushin-postgres-data → PostgreSQL relational data              │      │
│  │  ./logs → Application logs                                       │      │
│  └──────────────────────────────────────────────────────────────────┘      │
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
git clone https://github.com/iamveene/Tsushin.git
cd Tsushin

# Preferred: generate .env, network, and optional Caddy config automatically
python3 install.py

# Manual compose path: copy the environment template and edit it yourself
cp env.example .env

# Edit .env with your infrastructure settings
nano .env
```

### 2. Required Environment Variables

For manual compose deployments, configure these in `.env` at minimum:

```bash
# PostgreSQL
POSTGRES_PASSWORD=change-me

# Security
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
TSN_MASTER_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Docker-in-Docker bind mounts for runtime MCP/toolbox containers
HOST_BACKEND_DATA_PATH=/absolute/path/to/Tsushin/backend/data
```

Provider API keys are configured later through `/setup` and the Hub UI, not in `.env`.

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
- PostgreSQL database (via tsushin-postgres container)
- ChromaDB vector store
- Scheduler worker
- WebSocket support

**Volumes:**
- `./backend/data` → `/app/data` (database, vectors, workspace)
- `./logs/backend` → `/app/logs` (application logs)

### Frontend (tsushin-frontend)

Next.js 16 application with:
- Server-side rendering
- Standalone output mode

**Build Args:**
- `NEXT_PUBLIC_API_URL` - Backend API URL (default: http://localhost:8081)

### Tester MCP

WhatsApp bridge for QA testing. The current repository does not define a `testing` compose profile; Hub tester controls resolve a legacy tester container when present or fall back to the tenant's active runtime tester instance.

```bash
# Start the main stack
docker compose up -d
```

Local TTS (Kokoro) is no longer a compose profile. Create per-tenant instances via **Hub → Kokoro TTS → Setup with Wizard**; the backend auto-provisions a dedicated container per instance.

**Port:** 8088 when a standalone legacy tester container is running

## Common Commands

### Starting Services

```bash
# Start all services (background)
docker compose up -d

# Start with rebuild
docker compose up -d --build

# Start specific service
docker compose up -d backend
```

Kokoro TTS: no compose profile as of v0.7.0. Provision per-tenant instances via Hub → Kokoro TTS → Setup with Wizard.

### Stopping Services

```bash
# Stop all services without tearing down the shared network
docker compose stop

# Full reset (CAUTION: deletes data and removes compose containers; the external network remains)
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

Data is stored in bind-mounted volumes and named Docker volumes:

| Host Path / Volume | Container Path | Description |
|---------------------|----------------|-------------|
| `tsushin-postgres-data` (named volume) | `/var/lib/postgresql/data` | PostgreSQL relational data |
| `./backend/data/chroma/` | `/app/data/chroma/` | Vector embeddings |
| `./backend/data/mcp/` | `/app/data/mcp/` | MCP instance data |
| `./logs/backend/` | `/app/logs/` | Application logs |

### Backup

```bash
# Backup PostgreSQL database
docker exec tsushin-postgres pg_dump -U tsushin tsushin > backups/tsushin-$(date +%Y%m%d).sql

# Full data backup (ChromaDB, MCP data, logs)
tar -czvf backups/tsushin-data-$(date +%Y%m%d).tar.gz backend/data/
```

## Network Configuration

### Host Access from Container

Use `host.docker.internal` to access host services:

```bash
# Access Ollama on host
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

Kokoro TTS: the `KOKORO_SERVICE_URL` env fallback was removed in v0.7.0. Kokoro is now provisioned per tenant via Hub → Kokoro TTS → Setup with Wizard, which spawns a dedicated container and persists its URL in the `TTSInstance` row.

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

## Database Configuration

### Required Environment Variables

The PostgreSQL container requires these variables in your `.env`:

```bash
# PostgreSQL connection string (used by the backend)
DATABASE_URL=postgresql+asyncpg://tsushin:your_secure_password_here@tsushin-postgres:5432/tsushin

# PostgreSQL password (used by the postgres container)
POSTGRES_PASSWORD=your_secure_password_here
```

> Both values must use the same password. The installer sets these automatically.

### Rollback to SQLite

If you need to revert to SQLite (e.g., for local development without PostgreSQL):

1. Remove `DATABASE_URL` from your `.env` (or comment it out)
2. Restart the backend: `docker compose restart backend`

The backend will automatically fall back to the SQLite database at `backend/data/agent.db`.

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
# Check PostgreSQL tables
docker exec -it tsushin-postgres psql -U tsushin -d tsushin -c "\dt"

# Enter PostgreSQL shell
docker exec -it tsushin-postgres psql -U tsushin -d tsushin
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
- Frontend: Node 20, Next.js 16
- Tester MCP: Go 1.24, whatsmeow

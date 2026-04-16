# Upgrading to PostgreSQL

This guide walks you through migrating an existing Tsushin installation from SQLite to PostgreSQL. Your SQLite database is never modified during this process -- it is opened in read-only mode, so you can always roll back.

---

## Prerequisites

- An existing Tsushin installation with SQLite data (`backend/data/agent.db`)
- Docker and Docker Compose installed
- At least 1 GB of free disk space for PostgreSQL data

---

## Step 1: Update Your Environment

Add or update the following variable in your `.env` file at the project root:

```
POSTGRES_PASSWORD=<generate a secure password>
```

> **Tip:** Generate a strong password with `openssl rand -base64 24`.
>
> For local development, you can use any value (the default fallback is `tsushin_dev`).

---

## Step 2: Pull the Latest Code

```bash
git pull origin develop   # or the branch/tag you are tracking
```

---

## Step 3: Start PostgreSQL

Start only the PostgreSQL service first so it can initialize:

```bash
docker compose up -d postgres
```

Wait for the health check to confirm the database is ready:

```bash
docker compose exec postgres pg_isready -U tsushin -d tsushin
```

You should see: `localhost:5432 - accepting connections`

---

## Step 4: Build the Updated Backend

Rebuild the backend image without cache to ensure the latest migration scripts and ORM models are included:

```bash
docker compose build --no-cache backend
```

---

## Step 5: Run Schema Migrations

Apply all Alembic migrations to create the PostgreSQL schema:

```bash
docker compose run --rm backend python -c "
from alembic.config import Config
from alembic import command
import os

cfg = Config('alembic.ini')
cfg.set_main_option('sqlalchemy.url', os.environ['DATABASE_URL'])
command.upgrade(cfg, 'head')
"
```

This creates all tables, indexes, and constraints in PostgreSQL without touching your SQLite file.

---

## Step 6: Migrate Data from SQLite

Run the migration script to copy all your data from SQLite into PostgreSQL:

```bash
docker compose run --rm backend python scripts/migrate_sqlite_to_pg.py \
  --sqlite-url "sqlite:////app/data/agent.db" \
  --pg-url "postgresql://tsushin:YOUR_PASSWORD@postgres:5432/tsushin"
```

Replace `YOUR_PASSWORD` with the value you set for `POSTGRES_PASSWORD` in Step 1.

### Optional flags

| Flag            | Description                                         |
|-----------------|-----------------------------------------------------|
| `--dry-run`     | Count rows in each table without writing anything.   |
| `--batch-size N`| Number of rows per insert batch (default: 500).      |

**Recommended:** Run with `--dry-run` first to preview what will be migrated:

```bash
docker compose run --rm backend python scripts/migrate_sqlite_to_pg.py \
  --sqlite-url "sqlite:////app/data/agent.db" \
  --pg-url "postgresql://tsushin:YOUR_PASSWORD@postgres:5432/tsushin" \
  --dry-run
```

---

## Step 7: Start All Services

```bash
docker compose up -d
```

This starts PostgreSQL, the backend, and the frontend. The backend is configured to connect to PostgreSQL via the `DATABASE_URL` environment variable already set in `docker-compose.yml`.

---

## Step 8: Verify

Check that the backend is healthy:

```bash
curl http://localhost:8081/api/health
```

Then open the frontend (default: `http://localhost:3030`), log in with your existing credentials, and verify that your agents, conversations, flows, and settings are intact.

---

## Rollback

If something goes wrong, you can revert to SQLite without data loss:

1. **Stop all containers:**
   ```bash
   docker compose down
   ```

2. **Edit `docker-compose.yml`** -- in the backend environment section:
   - Comment out or remove the `DATABASE_URL` line:
     ```yaml
     # - DATABASE_URL=postgresql://tsushin:${POSTGRES_PASSWORD:-tsushin_dev}@postgres:5432/tsushin
     ```
   - Ensure the SQLite path is active:
     ```yaml
     - INTERNAL_DB_PATH=/app/data/agent.db
     ```

3. **Remove the `postgres` dependency** from the backend `depends_on` section (or simply don't start the postgres service).

4. **Restart:**
   ```bash
   docker compose up -d backend frontend
   ```

Your SQLite database was never modified -- the migration script opens it in read-only mode.

---

## Troubleshooting

### "permission denied" when connecting to PostgreSQL

Make sure the `POSTGRES_PASSWORD` value in your `.env` file matches what was used when the PostgreSQL container was first created. If you need to reset:

```bash
docker compose down
docker volume rm tsushin-postgres-data
docker compose up -d postgres
```

Then re-run Steps 5 and 6.

### Migration script reports skipped rows

The script logs warnings for rows that fail to insert (e.g., duplicate primary keys from a previous partial run). If you need to re-run the migration cleanly:

```bash
# Drop and recreate the PostgreSQL database
docker compose exec postgres psql -U tsushin -d postgres -c "DROP DATABASE tsushin;"
docker compose exec postgres psql -U tsushin -d postgres -c "CREATE DATABASE tsushin OWNER tsushin;"
```

Then re-run Steps 5 and 6.

### Backend fails to start after migration

Check the backend logs for details:

```bash
docker compose logs backend --tail 50
```

Common issues:
- **Missing environment variables:** Ensure `DATABASE_URL` is set in the backend environment.
- **PostgreSQL not ready:** The backend depends on `postgres` with a health check, but if the check is still running, wait a moment and try again.

---

## Notes

- **ChromaDB vector data** remains in `backend/data/chroma/` and is unaffected by this migration.
- **The SQLite file** (`backend/data/agent.db`) is preserved as a backup. You can safely keep it until you are confident the migration succeeded.
- **PostgreSQL data** is stored in the `tsushin-postgres-data` Docker volume, which persists across container restarts.
- **Sequence auto-increment** values are automatically reset by the migration script to continue from the highest existing ID.

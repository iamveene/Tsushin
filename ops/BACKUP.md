# Backup & Rollback Strategy

## Before Each Implementation

**Always create a backup before making significant changes:**

```bash
# Backup everything
python ops/backup.py

# Or backup specific components
python ops/backup.py --backend-only
python ops/backup.py --frontend-only
python ops/backup.py --db-only
```

Backups are stored in: `D:\code\tsushin\backups\`

## Rollback Process

If something breaks after an implementation:

### 1. Stop Running Services
```bash
# Stop frontend (Ctrl+C in terminal)
# Stop backend (Ctrl+C in terminal)
```

### 2. Identify Latest Backup
```bash
cd D:\code\tsushin\backups
dir /O-D  # Windows: List by newest first
```

### 3. Restore Backend
```bash
# Delete current backend
rmdir /s /q D:\code\tsushin\backend

# Restore from backup
xcopy /E /I /Y backups\backend_YYYYMMDD_HHMMSS D:\code\tsushin\backend
```

### 4. Restore Frontend
```bash
# Delete current frontend (keep node_modules)
rmdir /s /q D:\code\tsushin\frontend\app
rmdir /s /q D:\code\tsushin\frontend\components
rmdir /s /q D:\code\tsushin\frontend\lib

# Restore from backup
xcopy /E /I /Y backups\frontend_YYYYMMDD_HHMMSS D:\code\tsushin\frontend
```

### 5. Restore Database
```bash
# Copy database backup
copy /Y backups\agent_db_YYYYMMDD_HHMMSS\agent.db D:\code\tsushin\backend\data\agent.db
```

### 6. Restart Services
```bash
# Backend
cd D:\code\tsushin\backend
uvicorn app:app --host 127.0.0.1 --port 8081 --reload

# Frontend (in new terminal)
cd D:\code\tsushin\frontend
pnpm dev
```

## Backup Retention

- **Keep last 7 days** of backups for recent work
- **Keep 1 backup per week** for the last month
- **Delete backups older than 30 days** (unless marked as milestone)

### Manual Cleanup
```bash
# Delete backups older than 30 days
cd D:\code\tsushin\backups
# Review and delete manually, or use:
# forfiles /p . /s /m *.* /d -30 /c "cmd /c del @path"
```

## Git Integration

For code changes (not data):

```bash
# Before implementation
git add .
git commit -m "Pre-implementation snapshot: [Feature Name]"
git tag -a "pre-[feature]" -m "Backup before implementing [feature]"

# If rollback needed
git reset --hard pre-[feature]
```

## Best Practices

1. **Before Phase implementations**: Always backup
2. **Before database migrations**: Always backup database
3. **Before dependency updates**: Always backup
4. **After successful testing**: Tag backup as "stable"
5. **Document what changed**: Add notes to backup folder

## Emergency Recovery

If backups are corrupted or missing:

1. Check git history: `git log --oneline`
2. Restore from git tag: `git checkout [tag-name]`
3. Rebuild database from scratch: `python ops/seed_mcp_db.py`
4. Reconfigure from .env: Check `.env` file is correct

## Automated Backup (Future Enhancement)

Consider adding to Phase 4:
- Automated daily backups
- Cloud storage integration (S3, Google Drive)
- Backup verification scripts
- Automated rollback scripts

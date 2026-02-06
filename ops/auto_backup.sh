#!/bin/bash
# Automatic database backup script
# Runs daily to ensure we can recover from data loss incidents

cd /opt/tsushin/backend
source venv/bin/activate

# Create backup with timestamp
python3 ../ops/backup_database.py --message "Automatic daily backup"

# Keep only last 30 days of automatic backups (cleanup old ones)
find data/backups/ -name "agent_backup_*.db" -mtime +30 -delete
find data/backups/ -name "agent_backup_*.json" -mtime +30 -delete

echo "$(date): Automatic backup completed" >> /opt/tsushin/ops/backup.log

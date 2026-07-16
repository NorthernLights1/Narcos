#!/usr/bin/env bash
# Nightly backup (D13): database dump + media (attachments) together — a DB
# restore without the media folder gives you attachment rows pointing at
# nothing. Verifies the dump is listable before calling the backup good,
# logs a BACKUP event into the app's audit trail, keeps the newest 14.
#
# Environment:
#   NARCOS_BACKUP_ROOT   required — where backup folders are written
#   NARCOS_DB_PASSWORD   required
#   NARCOS_DB_NAME/USER/HOST/PORT  optional (narcos/narcos/localhost/5432)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${NARCOS_BACKUP_ROOT:?Set NARCOS_BACKUP_ROOT to the backup folder.}"
DB_NAME="${NARCOS_DB_NAME:-narcos}"
DB_USER="${NARCOS_DB_USER:-narcos}"
DB_HOST="${NARCOS_DB_HOST:-localhost}"
DB_PORT="${NARCOS_DB_PORT:-5432}"
: "${NARCOS_DB_PASSWORD:?Set NARCOS_DB_PASSWORD before running backup.}"
export PGPASSWORD="$NARCOS_DB_PASSWORD"

STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_ROOT/$STAMP"
mkdir -p "$TARGET"

pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -Fc \
    -f "$TARGET/narcos.dump" "$DB_NAME"
# A dump we cannot list is a dump we cannot restore — fail loudly now,
# not during a disaster.
pg_restore --list "$TARGET/narcos.dump" > /dev/null

if [ -d "$ROOT/media" ]; then
    tar -czf "$TARGET/media.tar.gz" -C "$ROOT" media
fi

"$ROOT/.venv/bin/python" "$ROOT/manage.py" log_ops_event BACKUP --detail "$TARGET"

# Retention: keep the newest 14 backup folders.
ls -1d "$BACKUP_ROOT"/*/ 2>/dev/null | sort -r | tail -n +15 | xargs -r rm -rf

echo "Backup written to $TARGET"

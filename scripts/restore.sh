#!/usr/bin/env bash
# Restore (D13). Two uses, same script:
#   Drill    — restore.sh /backups/STAMP           → scratch DB narcos_restore
#   Disaster — restore.sh /backups/STAMP narcos /app/media
# The target database is created fresh; an existing one is refused so a typo
# can never overwrite live data. MEDIA_TARGET (3rd arg) unpacks media.tar.gz
# so restored attachment rows point at real files again.
#
# Environment: NARCOS_DB_PASSWORD required;
#              NARCOS_DB_USER/HOST/PORT optional (narcos/localhost/5432)
set -euo pipefail

BACKUP_DIR="${1:?Usage: restore.sh BACKUP_DIR [TARGET_DB] [MEDIA_TARGET]}"
TARGET_DB="${2:-narcos_restore}"
MEDIA_TARGET="${3:-}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_USER="${NARCOS_DB_USER:-narcos}"
DB_HOST="${NARCOS_DB_HOST:-localhost}"
DB_PORT="${NARCOS_DB_PORT:-5432}"
: "${NARCOS_DB_PASSWORD:?Set NARCOS_DB_PASSWORD before running restore.}"
export PGPASSWORD="$NARCOS_DB_PASSWORD"

DUMP="$BACKUP_DIR/narcos.dump"
if [ ! -f "$DUMP" ]; then
    echo "Backup dump not found: $DUMP" >&2
    exit 1
fi

createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$TARGET_DB" \
    || { echo "createdb failed — target must not already exist." >&2; exit 1; }
pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TARGET_DB" "$DUMP"

if [ -n "$MEDIA_TARGET" ]; then
    if [ -f "$BACKUP_DIR/media.tar.gz" ]; then
        mkdir -p "$MEDIA_TARGET"
        # Archive entries start with "media/" — strip it so the files land
        # directly inside MEDIA_TARGET.
        tar -xzf "$BACKUP_DIR/media.tar.gz" -C "$MEDIA_TARGET" \
            --strip-components=1
        echo "Media unpacked into $MEDIA_TARGET"
    else
        echo "No media.tar.gz in $BACKUP_DIR — database restored, media skipped." >&2
    fi
fi

# Best effort: during bare-metal recovery the app environment may not be up
# yet, and the audit note must not fail the restore itself.
"$ROOT/.venv/bin/python" "$ROOT/manage.py" log_ops_event RESTORE \
    --detail "$TARGET_DB" \
    || echo "Warning: could not write RESTORE audit event." >&2

echo "Restored $BACKUP_DIR into database $TARGET_DB"

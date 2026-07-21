#!/bin/sh
# Narcos container entrypoint (D83): wait for Postgres, apply migrations
# (opt-out with NARCOS_AUTO_MIGRATE=0), then hand off to the CMD (waitress).
# The pre-migrate safety backup is taken by the deploy path (ops/deploy or
# ops/docker-backup.ps1), not here — a routine container restart re-runs a
# no-op migrate and must not dump every time.
set -e

echo "Waiting for PostgreSQL to accept connections..."
python - <<'PY'
import os
import sys
import time

import psycopg

dsn = (
    f"host={os.environ.get('NARCOS_DB_HOST', 'db')} "
    f"port={os.environ.get('NARCOS_DB_PORT', '5432')} "
    f"dbname={os.environ.get('NARCOS_DB_NAME', 'narcos')} "
    f"user={os.environ.get('NARCOS_DB_USER', 'narcos')} "
    f"password={os.environ.get('NARCOS_DB_PASSWORD', '')}"
)
for attempt in range(1, 61):
    try:
        psycopg.connect(dsn, connect_timeout=2).close()
        print("PostgreSQL is ready.")
        break
    except Exception:  # noqa: BLE001 — any connection error means "not ready yet"
        print(f"  ...not ready ({attempt}/60)", flush=True)
        time.sleep(2)
else:
    print("PostgreSQL did not become ready in time.", file=sys.stderr)
    sys.exit(1)
PY

if [ "${NARCOS_AUTO_MIGRATE:-1}" = "1" ]; then
    echo "Applying database migrations..."
    python manage.py migrate --noinput
else
    echo "NARCOS_AUTO_MIGRATE=0 — skipping automatic migrations."
fi

exec "$@"

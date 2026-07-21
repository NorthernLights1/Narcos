# Narcos Ops Runbook

This is the v1 go-live runbook (operational background: secrets, owner password
recovery, backup/restore *design*, disaster-recovery principles).

The production deployment is **Docker Desktop on a Windows 10 host** — the
step-by-step install, backup schedule, update, and disaster-recovery procedures
live in **[DEPLOYMENT.md](DEPLOYMENT.md)**, and the container-aware
`ops/docker-backup.ps1` / `ops/docker-restore.ps1` are the canonical tooling
there. The `scripts/backup.sh` + `scripts/restore.sh` (and their `.ps1` twins)
document the **host-installed, no-Docker alternative** and the shared restore
logic; the sections below apply to that path.

## Secrets and environment

Keep secrets outside source control in a local environment file or machine
environment variables:

- `NARCOS_SECRET_KEY`
- `NARCOS_DB_PASSWORD`
- `NARCOS_DB_NAME` default `narcos`
- `NARCOS_DB_USER` default `narcos`
- `NARCOS_DB_HOST` must stay `localhost`
- `NARCOS_DB_PORT` default `5432`
- `NARCOS_BACKUP_ROOT`, for example `D:\NarcosBackups`

PostgreSQL must listen on localhost only. Browsers talk to the Django app, not
to PostgreSQL.

## Owner password recovery

From the server console:

```powershell
.\.venv\Scripts\python.exe manage.py reset_owner_password owner_username
```

For a non-interactive emergency reset:

```powershell
.\.venv\Scripts\python.exe manage.py reset_owner_password owner_username --password "new-strong-password"
```

If there is exactly one owner user, the username can be omitted.

## Nightly backup

Put the environment in `/etc/narcos.env` (root-only readable) and add a cron
job (`crontab -e` as the app user):

```cron
0 22 * * * . /etc/narcos.env && /opt/narcos/scripts/backup.sh >> /var/log/narcos-backup.log 2>&1
```

`backup.sh` writes a `pg_dump` custom-format dump **and** `media.tar.gz`
(the attachments — a DB restore without media gives attachment rows that
point at nothing), verifies the dump is listable, logs a BACKUP event into
the app audit trail, and keeps the last 14 backup folders. Copy the backup
root to an external drive or cloud folder — a backup on the same disk dies
with the disk. The client still needs a UPS and backup drive before go-live.

Windows fallback: Task Scheduler running `scripts\backup.ps1` (same design).

**Docker note:** on the Docker deployment these host scripts do **not** run
unchanged — there is no host `.venv` or host `pg_dump`. Use
`ops/docker-backup.ps1` / `ops/docker-restore.ps1` instead, which run the same
logic *inside* the containers via `docker compose exec` (see
[DEPLOYMENT.md](DEPLOYMENT.md)). The principle is unchanged: back up with a
portable `pg_dump`, never `docker commit` or volume snapshots alone — a
`pg_dump` restores anywhere, a volume snapshot only restores into Docker.

## Restore drill

Before go-live, and before every update, prove the latest backup restores into
a scratch database:

```bash
NARCOS_DB_PASSWORD=... ./scripts/restore.sh /backups/YYYYMMDD-HHMMSS
```

This creates the scratch database `narcos_restore` and runs `pg_restore` into
it (an existing target database is refused — a typo can never overwrite
live). Add a third argument to also unpack media into a scratch folder:

```bash
./scripts/restore.sh /backups/YYYYMMDD-HHMMSS narcos_restore /tmp/narcos-media-drill
```

Then point a scratch app environment at `narcos_restore`, run:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py check
.venv/bin/python -m pytest
```

Only update the live database after the scratch restore and migration pass.
(Windows fallback: `restore.ps1 -BackupDir ... -MediaTarget ...`.)

## Bare-metal disaster recovery

The scenario the backups exist for: the server is dead, stolen, or
unbootable. Recovery point = the last nightly backup — **everything entered
after it is gone** (make sure the owner knows this; if a day of data is
unacceptable, schedule the backup more often).

On a fresh Linux machine:

1. Install PostgreSQL 16 and Python 3.12 (or Docker with the same images).
2. Get the application code at the **same version** that took the backup
   (`git clone` + checkout the release tag, or copy the release folder).
   Create the venv: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
3. Recreate the database role:
   `sudo -u postgres createuser --pwprompt narcos`
   (use the password from your secrets store; it must match `NARCOS_DB_PASSWORD`).
4. Copy the **newest backup folder** from the external drive / cloud onto
   the machine.
5. Restore as the real database and real media in one go:
   ```bash
   NARCOS_DB_PASSWORD=... ./scripts/restore.sh /backups/YYYYMMDD-HHMMSS narcos /opt/narcos/media
   ```
6. Write `/etc/narcos.env` with `NARCOS_SECRET_KEY`, `NARCOS_DB_PASSWORD`,
   `NARCOS_BACKUP_ROOT` (a fresh secret key is fine — it only logs everyone
   out; the database password must match step 3).
7. `manage.py migrate` (no-op when code and backup versions match), then
   `manage.py check`.
8. Start the service (waitress behind the same service manager as before,
   or `docker compose up -d`).
9. Prove it end to end before telling anyone it's fixed: log in, open the
   dashboard, open a document **that has an attachment** (this proves media
   came back, not just rows), print one document.
10. Re-enable the nightly backup cron on the new machine — a recovered
    server with no backups is the next disaster.

## Update procedure

1. Take a fresh backup.
2. Restore it to a scratch database.
3. Run migrations and tests against the scratch database.
4. Stop the live Waitress service.
5. Apply code and run `manage.py migrate` on live.
6. Run `manage.py check`.
7. Start the live Waitress service.
8. Open the dashboard and print one document.

## Windows service

Use NSSM or WinSW to run Waitress as a Windows service:

```powershell
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8000 narcos.wsgi:application
```

Set the service working directory to `C:\Projects\Narcos` and configure the
same environment variables listed above. Keep PostgreSQL as a separate Windows
service with automatic startup.

## Go-live checklist

- Server timezone is Africa/Addis_Ababa.
- PostgreSQL is bound to localhost only.
- `NARCOS_SECRET_KEY` and database password are unique and not committed.
- Owner password reset command has been tested.
- Latest backup restores into a scratch database.
- Printer works from the browser.
- Ethiopic names render in print.
- Withholding switches match the client's legal/accountant advice.
- Old paper/Excel process runs in parallel for 2 to 4 weeks.
- If LAN clients are added, give the server a stable IP or hostname.

# Narcos Ops Runbook

This is the v1 go-live runbook for one Windows server PC.

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

Create a Windows Task Scheduler job that runs every night:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Projects\Narcos\scripts\backup.ps1
```

The script writes a `pg_dump` custom-format dump and a `media.zip`, then keeps
the last 14 backup folders. Copy the backup root to an external drive or cloud
folder. The client still needs a UPS and backup drive before go-live.

## Restore drill

Before go-live, and before every update, prove the latest backup restores into
a scratch database:

```powershell
.\scripts\restore.ps1 -BackupDir D:\NarcosBackups\YYYYMMDD-HHMMSS -TargetDb narcos_restore
```

The restore script creates a scratch database and runs `pg_restore` into it.

Then point a scratch app environment at `narcos_restore`, run:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe -m pytest
```

Only update the live database after the scratch restore and migration pass.

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

# ops/docker-backup.ps1 — nightly backup for the Docker deployment (D83).
#
# Runs pg_dump inside the `db` container and archives media from the `app`
# container into <NARCOS_BACKUP_ROOT>\<stamp>\, copies .env alongside (the one
# recovery input not in git or the image), verifies the dump is listable, logs
# a BACKUP audit event, and prunes to 14 nightly + one per month for a year.
#
# Scheduling: Windows Task Scheduler, daily 16:00, with "Run task as soon as
# possible after a scheduled start is missed" ticked (unreliable power / PC may
# be off at 16:00). Must run from the deploy directory (compose.yml + .env).
param(
    [string]$BackupRoot = $env:NARCOS_BACKUP_ROOT
)
$ErrorActionPreference = "Stop"

# R69: DEPLOYMENT.md puts NARCOS_BACKUP_ROOT in .env, which Compose
# interpolates but PowerShell never reads — so the first scheduled run threw
# here before touching the database, and the nightly backup never existed.
# Read the same file Compose does, so there is one place to set it.
function Get-DotEnvValue([string]$Key) {
    if (-not (Test-Path ".\.env")) { return $null }
    foreach ($line in Get-Content ".\.env") {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=\s*(.*)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}
if (-not $BackupRoot) { $BackupRoot = Get-DotEnvValue "NARCOS_BACKUP_ROOT" }
if (-not $BackupRoot) {
    throw ("Set NARCOS_BACKUP_ROOT in .env next to compose.yml " +
           "(e.g. NARCOS_BACKUP_ROOT=C:\narcos\backups), or pass -BackupRoot.")
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $BackupRoot $stamp
New-Item -ItemType Directory -Force $target | Out-Null

# 1. Database dump (custom format) written into the mounted /backups.
docker compose exec -T db mkdir -p "/backups/$stamp"
docker compose exec -T db pg_dump -U narcos -Fc -f "/backups/$stamp/narcos.dump" narcos
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed." }

# 2. A dump we cannot list is a dump we cannot restore — fail now, not later.
docker compose exec -T db pg_restore --list "/backups/$stamp/narcos.dump" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Dump verification (pg_restore --list) failed." }

# 3. Media (attachments) — without them, restored attachment rows point at nothing.
# R69: this used to warn and carry on ("no media yet?"), which is the same
# excuse whether the folder is empty or the step is broken. Create the folder
# so an empty one archives cleanly, and treat anything else as a failure.
docker compose exec -T app sh -c "mkdir -p /app/media && tar czf /backups/$stamp/media.tar.gz -C /app media"
if ($LASTEXITCODE -ne 0) { throw "Media archive failed." }

# 4. .env — makes a wiped machine fully self-recoverable.
if (Test-Path ".\.env") { Copy-Item ".\.env" (Join-Path $target ".env") -Force }

# 5. Audit trail.
docker compose exec -T app python manage.py log_ops_event BACKUP --detail $stamp
if ($LASTEXITCODE -ne 0) { throw "Backup audit log failed." }

# 6. Retention: newest 14, plus the newest of each of the last 12 months.
$all = Get-ChildItem $BackupRoot -Directory | Sort-Object Name -Descending
$keep = [System.Collections.Generic.HashSet[string]]::new()
$all | Select-Object -First 14 | ForEach-Object { [void]$keep.Add($_.Name) }
$all | Group-Object { $_.Name.Substring(0, 6) } | Select-Object -First 12 | ForEach-Object {
    $newestOfMonth = $_.Group | Sort-Object Name -Descending | Select-Object -First 1
    [void]$keep.Add($newestOfMonth.Name)
}
$all | Where-Object { -not $keep.Contains($_.Name) } | Remove-Item -Recurse -Force

Write-Host "Backup written to $target"

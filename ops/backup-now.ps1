# ops/backup-now.ps1 - take one database backup right now, and stop.
#
# The emergency counterpart to docker-backup.ps1. Differences, all deliberate:
#
#   * It NEVER prunes. Retention is what nearly deleted the client's last good
#     backup (R97); an emergency backup must not be able to remove anything.
#   * A verified dump in hand beats an all-or-nothing run. docker-backup.ps1
#     throws if media or the audit log fails, which is right for a scheduled
#     job but wrong here - on a half-broken machine the app container may be
#     down while the database is perfectly readable. Those steps warn.
#   * It can copy straight onto a USB stick and check the copy arrived intact.
#
# Only the `db` container is required. Run from anywhere:
#
#   ops\backup-now.ps1                       -> into NARCOS_BACKUP_ROOT
#   ops\backup-now.ps1 -To E:\narcos-rescue  -> and copied onto the USB
#
param(
    [string]$To = "",
    [int]$WaitSeconds = 120
)
$ErrorActionPreference = "Stop"

function Find-DeployDir {
    # ops\ is not guaranteed to sit directly under the deploy directory - on
    # the client machine it turned up inside backups\. What actually defines
    # the deploy directory is compose.yml, so walk up until we find it.
    $d = $PSScriptRoot
    for ($i = 0; $i -lt 6 -and $d; $i++) {
        if (Test-Path (Join-Path $d "compose.yml")) { return $d }
        $d = Split-Path -Parent $d
    }
    throw "Could not find compose.yml at or above $PSScriptRoot. Copy this script into the deploy folder (the one holding compose.yml and .env) and run it from there."
}
$deployDir = Find-DeployDir
Set-Location $deployDir

function Wait-DockerEngine([int]$Seconds = 600) {
    # A catch-up run (StartWhenAvailable) fires minutes after login, while
    # Docker Desktop is often still starting - on the client's 8 GB machine
    # that takes several minutes. Without this the run throws immediately,
    # leaves a partial folder, and the day's backup silently does not exist.
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        docker version --format "{{.Server.Version}}" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Write-Host ("Waiting for the Docker engine... {0:N0}s" -f ((Get-Date) - $deadline.AddSeconds(-$Seconds)).TotalSeconds)
        Start-Sleep -Seconds 15
    }
    throw "Docker engine not available after $Seconds seconds. Is Docker Desktop running?"
}
Wait-DockerEngine

function Get-DotEnvValue([string]$Key) {
    if (-not (Test-Path ".\.env")) { return $null }
    foreach ($line in Get-Content ".\.env") {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=\s*(.*)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

$backupRoot = Get-DotEnvValue "NARCOS_BACKUP_ROOT"
if (-not $backupRoot) { $backupRoot = Join-Path $deployDir "backups" }
$stamp = "manual-" + (Get-Date -Format "yyyyMMdd-HHmmss")
$target = Join-Path $backupRoot $stamp

Write-Host "== 1/5  Starting the database =="
docker compose up -d db
if ($LASTEXITCODE -ne 0) { throw "Could not start the db container. Is Docker Desktop running? See DEPLOYMENT.md section 6." }

# The healthcheck uses pg_isready; so do we, so "ready" means the same thing.
$deadline = (Get-Date).AddSeconds($WaitSeconds)
$ready = $false
while ((Get-Date) -lt $deadline) {
    docker compose exec -T db pg_isready -U narcos -d narcos 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 3
}
if (-not $ready) { throw "Database did not become ready within $WaitSeconds s. Check: docker compose logs db" }
Write-Host "Database is accepting connections."

Write-Host "== 2/5  Dumping =="
New-Item -ItemType Directory -Force $target | Out-Null
docker compose exec -T db mkdir -p "/backups/$stamp"
docker compose exec -T db pg_dump -U narcos -Fc -f "/backups/$stamp/narcos.dump" narcos
if ($LASTEXITCODE -ne 0) { throw "pg_dump FAILED. Nothing was saved." }

Write-Host "== 3/5  Verifying the dump is restorable =="
# A dump we cannot list is a dump we cannot restore. This is the only step
# that proves the file is worth keeping, so it is fatal.
$tables = docker compose exec -T db pg_restore --list "/backups/$stamp/narcos.dump" |
          Select-String -Pattern "TABLE DATA" | Measure-Object | Select-Object -ExpandProperty Count
if ($LASTEXITCODE -ne 0) { throw "Dump verification failed - treat the file as unusable." }
Write-Host "Verified. $tables tables with data."
# Proof of verification. Without it, a backup taken while the app container is
# down (no media.tar.gz) looks identical to one cut short by a power failure.
Set-Content (Join-Path $target "VERIFIED.txt") ("narcos.dump verified restorable {0}; {1} tables with data." -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $tables)

Write-Host "== 4/5  Media and .env (best effort) =="
docker compose up -d app 2>&1 | Out-Null
docker compose exec -T app sh -c "mkdir -p /app/media && tar czf /backups/$stamp/media.tar.gz -C /app media" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Warning "Media archive FAILED - attachments are not in this backup. The database is." }
else { Write-Host "Media archived." }

if (Test-Path ".\.env") { Copy-Item ".\.env" (Join-Path $target ".env") -Force; Write-Host ".env copied." }
else { Write-Warning "No .env beside compose.yml - a bare-metal restore will need it rebuilt by hand." }

docker compose exec -T app python manage.py log_ops_event BACKUP --detail $stamp 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Warning "Could not write the BACKUP audit row (app container down?). The backup itself is fine." }

Write-Host "== 5/5  Result =="
# -Force, or dotfiles are skipped: .env is the one recovery input not in git
# or the image, and without it a bare-metal restore cannot be completed.
$files = Get-ChildItem $target -File -Force
foreach ($f in $files) { "  {0}  {1} MB" -f $f.Name, ([math]::Round($f.Length / 1MB, 2)) | Write-Host }

if ($To) {
    $dest = Join-Path $To $stamp
    New-Item -ItemType Directory -Force $dest | Out-Null
    foreach ($f in $files) { Copy-Item $f.FullName (Join-Path $dest $f.Name) -Force }
    # Verify the copy, because a USB stick that silently truncates is the
    # classic way an "offsite backup" turns out not to exist.
    $bad = @()
    foreach ($f in $files) {
        $c = Join-Path $dest $f.Name
        if (-not (Test-Path $c) -or (Get-Item $c -Force).Length -ne $f.Length) { $bad += $f.Name }
    }
    if ($bad) { throw ("Copy to {0} is INCOMPLETE: {1}. Do not remove the USB - try again." -f $dest, ($bad -join ", ")) }
    Write-Host "Copied and size-checked onto $dest"
}

Write-Host ""
Write-Host "Backup complete: $target"
if ($To) { Write-Host ("Second copy:     " + (Join-Path $To $stamp)) }
Write-Host "Nothing was deleted. Photograph this window."

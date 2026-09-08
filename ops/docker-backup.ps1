# ops/docker-backup.ps1 - nightly backup for the Docker deployment (D83).
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

# R99: this ran from whatever directory Task Scheduler happened to give it, and
# read .env relatively. A task whose "Start in" is unset or wrong therefore
# failed every day, and a scheduled job that fails is silent by nature - which
# is the whole reason the client went a month with no backup. Locate the deploy
# directory from the script's own location instead.
function Find-DeployDir {
    $d = $PSScriptRoot
    for ($i = 0; $i -lt 6 -and $d; $i++) {
        if (Test-Path (Join-Path $d "compose.yml")) { return $d }
        $d = Split-Path -Parent $d
    }
    throw "Could not find compose.yml at or above $PSScriptRoot."
}
Set-Location (Find-DeployDir)

# R69: DEPLOYMENT.md puts NARCOS_BACKUP_ROOT in .env, which Compose
# interpolates but PowerShell never reads - so the first scheduled run threw
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

# 2. A dump we cannot list is a dump we cannot restore - fail now, not later.
docker compose exec -T db pg_restore --list "/backups/$stamp/narcos.dump" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Dump verification (pg_restore --list) failed." }

# 3. Media (attachments) - without them, restored attachment rows point at nothing.
# R69: this used to warn and carry on ("no media yet?"), which is the same
# excuse whether the folder is empty or the step is broken. Create the folder
# so an empty one archives cleanly, and treat anything else as a failure.
docker compose exec -T app sh -c "mkdir -p /app/media && tar czf /backups/$stamp/media.tar.gz -C /app media"
if ($LASTEXITCODE -ne 0) { throw "Media archive failed." }

# 4. .env - makes a wiped machine fully self-recoverable.
if (Test-Path ".\.env") { Copy-Item ".\.env" (Join-Path $target ".env") -Force }

# 5. Audit trail.
docker compose exec -T app python manage.py log_ops_event BACKUP --detail $stamp
if ($LASTEXITCODE -ne 0) { throw "Backup audit log failed." }

# 6. Retention: newest 14 complete, plus the newest complete of each of the
# last 12 months.
#
# R97: this used to count *every* directory under the backup root. Step 0
# creates <stamp>\ before the dump runs, so a crash or a throw at any later
# step leaves a folder holding nothing restorable. On the client machine the
# power cuts produced a run of those. They sorted newest-first alongside real
# backups, filled the fourteen keep slots, and the next successful run would
# have deleted the last good backup while reporting success. A folder is a
# backup only if it holds a non-empty dump AND the media archive.
function Test-CompleteBackup([System.IO.DirectoryInfo]$Dir) {
    $dump = Join-Path $Dir.FullName "narcos.dump"
    $media = Join-Path $Dir.FullName "media.tar.gz"
    if (-not (Test-Path $dump)) { return $false }
    if ((Get-Item $dump).Length -le 0) { return $false }
    return (Test-Path $media)
}

# Retention deletes things, so it may only ever look at folders it is certain
# it created. On the client machine `ops\` turned out to live inside the backup
# root; without this filter it is "a folder with no dump", i.e. wreckage, and
# gets removed along with every script in it. Only scheduled stamps
# (20260807-160000) are candidates. Manual backups from backup-now.ps1 are
# deliberate acts and are never auto-pruned. Anything else is left alone.
$stampLike = '^\d{8}-\d{6}$'
$all = Get-ChildItem $BackupRoot -Directory |
       Where-Object { $_.Name -match $stampLike } |
       Sort-Object Name -Descending
$complete = @($all | Where-Object { Test-CompleteBackup $_ })
$partial = @($all | Where-Object { -not (Test-CompleteBackup $_) })

$keep = [System.Collections.Generic.HashSet[string]]::new()
$complete | Select-Object -First 14 | ForEach-Object { [void]$keep.Add($_.Name) }
$complete | Group-Object { $_.Name.Substring(0, 6) } | Select-Object -First 12 | ForEach-Object {
    $newestOfMonth = $_.Group | Sort-Object Name -Descending | Select-Object -First 1
    [void]$keep.Add($newestOfMonth.Name)
}
$complete | Where-Object { -not $keep.Contains($_.Name) } | Remove-Item -Recurse -Force

# Wreckage of a failed run: nothing to restore from, but it is the evidence
# that runs are failing. Keep a week of it, then bin it.
$cutoff = (Get-Date).AddDays(-7)
$partial | Where-Object { $_.CreationTime -lt $cutoff } | Remove-Item -Recurse -Force
if ($partial.Count -gt 0) {
    Write-Warning ("{0} incomplete backup folder(s) under $BackupRoot - earlier runs failed. Investigate before trusting the schedule." -f $partial.Count)
}

Write-Host "Backup written to $target"

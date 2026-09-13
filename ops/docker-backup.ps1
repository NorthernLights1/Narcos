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

# R100: powershell.exe -File exits 0 even when the script threw, so Task
# Scheduler reported LastTaskResult=0 for runs that produced no backup at all.
# A scheduled job whose only signal is a success code that always says success
# is worse than no job. Fail loudly, in the exit code and on disk.
$LogFile = Join-Path $PSScriptRoot "backup.log"
function Write-BackupLog([string]$Line) {
    Write-Host $Line
    try { Add-Content -Path $LogFile -Value $Line } catch { }
}
trap {
    Write-BackupLog ("BACKUP FAILED {0} - {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $_.Exception.Message)
    exit 1
}

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

# D147: the owner sets the paths, the interval and the retention count in the
# app, which writes them into <BackupRoot>\schedule.json through the mount both
# containers share. A missing or unreadable file is not an error - it means the
# settings have never been saved, and today's behaviour is exactly right.
$Schedule = $null
$schedulePath = Join-Path $BackupRoot "schedule.json"
if (Test-Path $schedulePath) {
    try { $Schedule = Get-Content $schedulePath -Raw | ConvertFrom-Json }
    catch { Write-BackupLog ("schedule.json is unreadable ({0}) - using the built-in defaults." -f $_.Exception.Message) }
}
function Setting([string]$Name, $Fallback) {
    if ($Schedule -and $null -ne $Schedule.$Name -and "$($Schedule.$Name)" -ne "") { return $Schedule.$Name }
    return $Fallback
}
$IntervalDays  = [int](Setting "interval_days" 1)
$KeepCount     = [int](Setting "keep_count" 14)
$PrimaryPath   = [string](Setting "primary_path" "")
$SecondaryPath = [string](Setting "secondary_path" "")

# A folder is a backup only if it holds a non-empty dump AND the media archive
# (R97 - a folder created and then abandoned by a power cut is not a backup,
# and counting it as one nearly deleted the last good copy).
function Test-CompleteBackup([System.IO.DirectoryInfo]$Dir) {
    $dump = Join-Path $Dir.FullName "narcos.dump"
    $media = Join-Path $Dir.FullName "media.tar.gz"
    if (-not (Test-Path $dump)) { return $false }
    if ((Get-Item $dump).Length -le 0) { return $false }
    return (Test-Path $media)
}

$stampLike = '^\d{8}-\d{6}$'
function Get-CompleteBackups([string]$Root) {
    if (-not (Test-Path $Root)) { return @() }
    return @(Get-ChildItem $Root -Directory |
             Where-Object { $_.Name -match $stampLike } |
             Where-Object { Test-CompleteBackup $_ } |
             Sort-Object Name -Descending)
}

# The interval only ever stretches the gap; it can never make the job run more
# often than Task Scheduler starts it, and it can never skip when there is no
# good backup to fall back on.
if ($IntervalDays -gt 1) {
    $newest = Get-CompleteBackups $BackupRoot | Select-Object -First 1
    if ($newest) {
        $age = (Get-Date) - [datetime]::ParseExact($newest.Name, "yyyyMMdd-HHmmss", $null)
        if ($age.TotalDays -lt $IntervalDays) {
            Write-BackupLog ("BACKUP SKIPPED {0} - last good backup {1} is {2:N1} day(s) old; the interval is {3}." -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $newest.Name, $age.TotalDays, $IntervalDays)
            exit 0
        }
    }
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

# 6. Copies. The dump has to land in the mounted folder - that is the only
# path both containers can write - so the configured destinations are copies
# made here on the host, afterwards, and each one is checked by size.
function Copy-BackupTo([string]$Destination, [switch]$Fatal) {
    if (-not $Destination) { return $false }
    if ((Resolve-Path -LiteralPath $BackupRoot -ErrorAction SilentlyContinue).Path -eq
        (Resolve-Path -LiteralPath $Destination -ErrorAction SilentlyContinue).Path) {
        return $true   # already there
    }
    try {
        $dest = Join-Path $Destination $stamp
        New-Item -ItemType Directory -Force $dest | Out-Null
        $files = Get-ChildItem $target -File -Force
        foreach ($f in $files) { Copy-Item $f.FullName (Join-Path $dest $f.Name) -Force }
        # A drive that silently truncates is the classic way an offsite copy
        # turns out not to exist. Compare sizes, every file, every run.
        $bad = @()
        foreach ($f in $files) {
            $c = Join-Path $dest $f.Name
            if (-not (Test-Path $c) -or (Get-Item $c -Force).Length -ne $f.Length) { $bad += $f.Name }
        }
        if ($bad) { throw ("incomplete: " + ($bad -join ", ")) }
        Write-BackupLog ("Copied to {0}" -f $dest)
        return $true
    } catch {
        $message = "Copy to {0} FAILED - {1}" -f $Destination, $_.Exception.Message
        if ($Fatal) { throw $message }
        # A USB stick left unplugged must never cost the backup that did work.
        Write-BackupLog ("WARNING  " + $message)
        return $false
    }
}

[void](Copy-BackupTo $PrimaryPath -Fatal)
[void](Copy-BackupTo $SecondaryPath)

# 7. Retention, per destination: the newest $KeepCount complete backups, plus
# the newest complete of each of the last 12 months.
#
# R97: this used to count *every* directory under the backup root. The folder
# is created before the dump runs, so a crash at any later step leaves one
# holding nothing restorable. On the client machine the power cuts produced a
# run of those. They sorted newest-first alongside real backups, filled the
# keep slots, and the next successful run would have deleted the last good
# backup while reporting success.
#
# Retention deletes things, so it may only ever look at folders it is certain
# it created: scheduled stamps (20260807-160000) and nothing else. On the
# client machine `ops\` turned out to live inside the backup root, and without
# that filter it is "a folder with no dump" - wreckage - and goes, with every
# script in it. Manual backups from backup-now.ps1 are deliberate acts and are
# never auto-pruned.
function Invoke-Retention([string]$Root) {
    if (-not (Test-Path $Root)) { return }
    $all = Get-ChildItem $Root -Directory |
           Where-Object { $_.Name -match $stampLike } |
           Sort-Object Name -Descending
    $complete = @($all | Where-Object { Test-CompleteBackup $_ })
    $partial = @($all | Where-Object { -not (Test-CompleteBackup $_) })

    # Nothing good to keep means nothing may be deleted. Without this a
    # destination that has only ever failed would prune its own evidence.
    if ($complete.Count -eq 0) { return }

    $keep = [System.Collections.Generic.HashSet[string]]::new()
    # The newest complete backup is never removable, whatever the count says.
    [void]$keep.Add($complete[0].Name)
    $complete | Select-Object -First $KeepCount | ForEach-Object { [void]$keep.Add($_.Name) }
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
        Write-Warning ("{0} incomplete backup folder(s) under {1} - earlier runs failed. Investigate before trusting the schedule." -f $partial.Count, $Root)
    }
}

Invoke-Retention $BackupRoot
if ($PrimaryPath) { Invoke-Retention $PrimaryPath }
if ($SecondaryPath) { Invoke-Retention $SecondaryPath }

Write-BackupLog ("BACKUP OK {0} - {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $target)
exit 0

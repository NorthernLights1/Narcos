param(
    [Parameter(Mandatory = $true)][string]$BackupDir,
    [string]$TargetDb = "narcos_restore",
    [string]$MediaTarget = "",
    [string]$DbUser = $(if ($env:NARCOS_DB_USER) { $env:NARCOS_DB_USER } else { "narcos" }),
    [string]$DbHost = $(if ($env:NARCOS_DB_HOST) { $env:NARCOS_DB_HOST } else { "localhost" }),
    [string]$DbPort = $(if ($env:NARCOS_DB_PORT) { $env:NARCOS_DB_PORT } else { "5432" }),
    [string]$DbPassword = $env:NARCOS_DB_PASSWORD
)

if (-not $DbPassword) { throw "Set NARCOS_DB_PASSWORD before running restore." }

$dump = Join-Path $BackupDir "narcos.dump"
if (-not (Test-Path $dump)) { throw "Backup dump not found: $dump" }

$env:PGPASSWORD = $DbPassword
& createdb -h $DbHost -p $DbPort -U $DbUser $TargetDb
if ($LASTEXITCODE -ne 0) { throw "createdb failed. Use a new scratch database name." }

& pg_restore -h $DbHost -p $DbPort -U $DbUser -d $TargetDb $dump
if ($LASTEXITCODE -ne 0) { throw "pg_restore failed." }

# Media restore: without it, restored attachment rows point at nothing.
if ($MediaTarget) {
    $mediaZip = Join-Path $BackupDir "media.zip"
    if (Test-Path $mediaZip) {
        $staging = Join-Path $env:TEMP ("narcos-media-" + (Get-Date -Format "yyyyMMddHHmmss"))
        Expand-Archive -Path $mediaZip -DestinationPath $staging -Force
        New-Item -ItemType Directory -Force $MediaTarget | Out-Null
        # The zip's root is the "media" folder itself — copy its contents.
        Copy-Item -Path (Join-Path $staging "media\*") -Destination $MediaTarget -Recurse -Force
        Remove-Item -Recurse -Force $staging
        Write-Host "Media unpacked into $MediaTarget"
    } else {
        Write-Warning "No media.zip in $BackupDir - database restored, media skipped."
    }
}

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
& $python (Join-Path $root "manage.py") log_ops_event RESTORE --detail $TargetDb
if ($LASTEXITCODE -ne 0) { throw "Restore audit log failed." }

Write-Host "Restored $BackupDir into database $TargetDb"

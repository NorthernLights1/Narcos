param(
    [string]$BackupRoot = $env:NARCOS_BACKUP_ROOT,
    [string]$DbName = $(if ($env:NARCOS_DB_NAME) { $env:NARCOS_DB_NAME } else { "narcos" }),
    [string]$DbUser = $(if ($env:NARCOS_DB_USER) { $env:NARCOS_DB_USER } else { "narcos" }),
    [string]$DbHost = $(if ($env:NARCOS_DB_HOST) { $env:NARCOS_DB_HOST } else { "localhost" }),
    [string]$DbPort = $(if ($env:NARCOS_DB_PORT) { $env:NARCOS_DB_PORT } else { "5432" }),
    [string]$DbPassword = $env:NARCOS_DB_PASSWORD
)

if (-not $BackupRoot) { throw "Set NARCOS_BACKUP_ROOT to the backup folder." }
if (-not $DbPassword) { throw "Set NARCOS_DB_PASSWORD before running backup." }

$root = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $BackupRoot $stamp
New-Item -ItemType Directory -Force $target | Out-Null

$env:PGPASSWORD = $DbPassword
$dump = Join-Path $target "narcos.dump"
& pg_dump -h $DbHost -p $DbPort -U $DbUser -Fc -f $dump $DbName
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed." }

$media = Join-Path $root "media"
if (Test-Path $media) {
    Compress-Archive -Path $media -DestinationPath (Join-Path $target "media.zip") -Force
}

$python = Join-Path $root ".venv\Scripts\python.exe"
& $python (Join-Path $root "manage.py") log_ops_event BACKUP --detail $target
if ($LASTEXITCODE -ne 0) { throw "Backup audit log failed." }

Get-ChildItem $BackupRoot -Directory |
    Sort-Object Name -Descending |
    Select-Object -Skip 14 |
    Remove-Item -Recurse -Force

Write-Host "Backup written to $target"

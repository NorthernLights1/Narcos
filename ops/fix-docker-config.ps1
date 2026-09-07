# ops/fix-docker-config.ps1 - repair Docker Desktop config zero-filled by a
# power cut, so it will start again.
#
# Seen on the client machine 2026-09-07 (photo of the dialog):
#   loading/formatting daemon.json: parsing daemon config
#   C:\Users\hp\.docker\daemon.json: parsing JSON:
#   invalid character '\x00' looking for beginning of value
#
# NTFS commits a file's new size before its contents reach the disk. Cut the
# power in between and the file reads back as a run of NUL bytes. Docker
# Desktop then refuses to start, and the dialog it shows offers "Reset to
# factory defaults" - which deletes named volumes, i.e. the whole database.
# This script is the safe alternative: it quarantines the unreadable config
# files (renames, never deletes) and lets Docker Desktop recreate defaults.
#
# Touches nothing but Docker's own settings. Volumes are not involved.
# Run as the signed-in user, with Docker Desktop closed:
#
#   powershell -ExecutionPolicy Bypass -File ops\fix-docker-config.ps1
#
$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

$candidates = @(
    (Join-Path $env:USERPROFILE ".docker\daemon.json"),
    (Join-Path $env:USERPROFILE ".docker\config.json"),
    (Join-Path $env:APPDATA "Docker\settings.json"),
    (Join-Path $env:APPDATA "Docker\settings-store.json"),
    (Join-Path $env:USERPROFILE ".wslconfig")
)

function Test-FileUsable([string]$Path) {
    # Three ways a power cut leaves a config file unusable.
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -eq 0) { return "empty" }
    if ($bytes -contains 0) { return "NUL bytes (zero-filled by a power cut)" }
    if ($Path -like "*.json") {
        try { [void]([System.IO.File]::ReadAllText($Path) | ConvertFrom-Json) }
        catch { return "not valid JSON" }
    }
    return $null
}

$quarantined = 0
foreach ($path in $candidates) {
    if (-not (Test-Path $path)) { Write-Host ("skip   {0}  (not present)" -f $path); continue }
    $problem = Test-FileUsable $path
    if (-not $problem) { Write-Host ("ok     {0}" -f $path); continue }

    $dead = "$path.corrupt-$stamp"
    Move-Item $path $dead -Force
    Write-Warning ("BAD    {0} - {1}" -f $path, $problem)
    Write-Host   ("       moved aside to {0}" -f $dead)
    $quarantined++
}

Write-Host ""
if ($quarantined -eq 0) {
    Write-Host "No damaged Docker config found. If Docker Desktop still will not"
    Write-Host "start, photograph the error dialog - the message names the file."
}
else {
    Write-Host "$quarantined file(s) moved aside. Now start Docker Desktop; it"
    Write-Host "recreates them with defaults. This deployment needs no custom"
    Write-Host "daemon settings, so defaults are correct."
    Write-Host ""
    Write-Host "Then, from C:\narcos:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File ops\backup-now.ps1 -To E:\narcos-rescue"
}

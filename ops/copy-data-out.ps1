# ops/copy-data-out.ps1 - get the client's data onto a USB stick when Docker
# will not start. Needs no Docker, no engine, no containers.
#
# Two things get copied:
#   1. C:\narcos\backups   - dumps taken previously. Plain files on Windows.
#   2. The WSL2 disk file  - where the live database actually lives. Copying
#      it is the only way to reach the current data with the engine dead.
#
# It copies. It never deletes, restores, or repairs anything.
#
#   powershell -ExecutionPolicy Bypass -File ops\copy-data-out.ps1 -To E:\narcos-rescue
#
param(
    [Parameter(Mandatory = $true)][string]$To
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

function Get-DotEnvValue([string]$Key) {
    $envFile = Join-Path $deployDir ".env"
    if (-not (Test-Path $envFile)) { return $null }
    foreach ($line in Get-Content $envFile) {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=\s*(.*)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}
New-Item -ItemType Directory -Force $To | Out-Null
Start-Transcript -Path (Join-Path $To "copy-log.txt") -Append | Out-Null

Write-Host "== 1/2  Existing backups =="
$backupRoot = Get-DotEnvValue "NARCOS_BACKUP_ROOT"
if (-not $backupRoot) { $backupRoot = Join-Path $deployDir "backups" }
Write-Host "Backup root: $backupRoot"
if (Test-Path $backupRoot) {
    # Only folders this system creates are backups. ops\ lives in here on the
    # client machine; listing it as a failed backup would just alarm people.
    $stampLike = '^(manual-)?\d{8}-\d{6}$'
    foreach ($f in (Get-ChildItem $backupRoot -Directory | Where-Object { $_.Name -match $stampLike } | Sort-Object Name)) {
        $files = Get-ChildItem $f.FullName -File -Force
        # media.tar.gz is written only after the dump is verified restorable,
        # so its presence is what tells you a run actually finished (R97).
        $dump = $files | Where-Object { $_.Name -eq "narcos.dump" -and $_.Length -gt 0 }
        $media = $files | Where-Object { $_.Name -eq "media.tar.gz" }
        $verified = $files | Where-Object { $_.Name -eq "VERIFIED.txt" }
        $state = if ($dump -and ($media -or $verified)) { "complete" }
                 elseif ($dump) { "SUSPECT - not verified" }
                 else { "INCOMPLETE - no dump" }
        "  {0}  {1} MB  {2}" -f $f.Name, [math]::Round((($files | Measure-Object Length -Sum).Sum / 1MB), 2), $state | Write-Host
    }
    robocopy $backupRoot (Join-Path $To "backups") /E /R:3 /W:5 /NP /NFL /NDL | Out-Null
    if ($LASTEXITCODE -ge 8) { Write-Warning "robocopy reported failures (exit $LASTEXITCODE)." }
    else { Write-Host "  copied to $To\backups" }
}
else { Write-Warning "No backups folder at $backupRoot" }

Write-Host ""
Write-Host "== 2/2  The WSL2 disk (the live database) =="
Write-Host "Stopping WSL so the file is not locked or half-written ..."
wsl --shutdown
Start-Sleep -Seconds 10

$wslRoot = Join-Path $env:LOCALAPPDATA "Docker\wsl"
$disks = @()
if (Test-Path $wslRoot) { $disks = @(Get-ChildItem $wslRoot -Recurse -Filter *.vhdx -ErrorAction SilentlyContinue) }
if ($disks.Count -eq 0) { Write-Warning "No .vhdx under $wslRoot. Run 'wsl -l -v' and send a photo." }

$freeGB = (Get-PSDrive $To.Substring(0, 1)).Free / 1GB
Write-Host ("Destination has {0} GB free." -f [math]::Round($freeGB, 2))
foreach ($d in $disks) {
    $gb = [math]::Round($d.Length / 1GB, 2)
    Write-Host ("  {0}  ({1} GB)" -f $d.FullName, $gb)
    if ($freeGB -lt $gb) { Write-Warning ("  SKIPPED - needs {0} GB, only {1} GB free." -f $gb, [math]::Round($freeGB, 2)); continue }
    robocopy $d.DirectoryName (Join-Path $To ("wsl-disk\" + $d.Directory.Name)) $d.Name /R:3 /W:5 /NP /NFL /NDL | Out-Null
    if ($LASTEXITCODE -ge 8) { Write-Warning ("  copy FAILED (exit {0}) - do not remove the USB, run again." -f $LASTEXITCODE) }
    else { Write-Host "  copied." }
}

Write-Host ""
Write-Host "Done. Everything is under $To"
Write-Host "Nothing on this machine was changed or deleted."
Stop-Transcript | Out-Null

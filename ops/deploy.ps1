# ops/deploy.ps1 — update the running deployment safely (D83).
#
# One command for a version update: take a fresh backup, pull the new image,
# recreate the app (the entrypoint auto-applies migrations on start). Running
# updates through this script is what guarantees "backup before migrate" — a
# bare `docker compose pull; up -d` skips the safety backup.
#
# Run from the deploy directory (compose.yml + .env). Requires internet for the
# pull; offline updates use `docker load` from a USB image tar instead.
$ErrorActionPreference = "Stop"

Write-Host "== 1/3  Taking a fresh backup before changing anything =="
& (Join-Path $PSScriptRoot "docker-backup.ps1")

Write-Host "== 2/3  Pulling the new image =="
docker compose pull app
if ($LASTEXITCODE -ne 0) { throw "docker compose pull failed (no internet? use docker load from USB)." }

Write-Host "== 3/3  Recreating the app (migrations run on start) =="
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed." }

docker compose ps
Write-Host "Update complete. Open the app and confirm the dashboard loads, then print one document."

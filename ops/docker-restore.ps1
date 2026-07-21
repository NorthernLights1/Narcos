# ops/docker-restore.ps1 — restore a Docker-deployment backup (D83).
#
#   Drill (safe, default):  ops\docker-restore.ps1 20260717-160000
#       -> restores into scratch DB `narcos_restore`, leaves live untouched.
#   Disaster (into live):   ops\docker-restore.ps1 20260717-160000 narcos /app/media
#       -> restores into `narcos` ONLY if it is empty (fresh machine), and
#          unpacks media. Refuses a database that already has tables, so a
#          typo can never overwrite live data.
#
# Run from the deploy directory. For a disaster restore into live, bring up
# ONLY the db first (`docker compose up -d db`), restore, then start the app.
param(
    [Parameter(Mandatory = $true)][string]$Stamp,
    [string]$TargetDb = "narcos_restore",
    [string]$MediaTarget = ""
)
$ErrorActionPreference = "Stop"

$dump = "/backups/$Stamp/narcos.dump"
docker compose exec -T db test -f $dump
if ($LASTEXITCODE -ne 0) { throw "Backup dump not found: $dump" }

# Create the target if absent; if present it must be empty, or we refuse.
$exists = (docker compose exec -T db psql -U narcos -tAc "SELECT 1 FROM pg_database WHERE datname='$TargetDb'").Trim()
if ($exists -ne "1") {
    docker compose exec -T db createdb -U narcos $TargetDb
    if ($LASTEXITCODE -ne 0) { throw "createdb '$TargetDb' failed." }
}
else {
    $tables = (docker compose exec -T db psql -U narcos -d $TargetDb -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").Trim()
    if ([int]$tables -gt 0) {
        throw "Database '$TargetDb' already has $tables tables — refusing to overwrite. Use a scratch name for a drill."
    }
}

docker compose exec -T db pg_restore -U narcos -d $TargetDb $dump
if ($LASTEXITCODE -ne 0) { throw "pg_restore failed." }

if ($MediaTarget) {
    docker compose exec -T app sh -c "mkdir -p '$MediaTarget' && tar xzf /backups/$Stamp/media.tar.gz -C '$MediaTarget' --strip-components=1"
    if ($LASTEXITCODE -ne 0) { Write-Warning "Media unpack failed or media.tar.gz missing — DB restored, media skipped." }
    else { Write-Host "Media unpacked into $MediaTarget" }
}

# Best-effort audit note; during bare-metal recovery the app may not be up yet.
docker compose exec -T app python manage.py log_ops_event RESTORE --detail $TargetDb 2>$null

Write-Host "Restored /backups/$Stamp into database '$TargetDb'."

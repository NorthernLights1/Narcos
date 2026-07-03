# Build static/css/app.css from static/src/input.css using the Tailwind
# standalone CLI (D55 — no Node project). Downloads the CLI on first run.
$root = Split-Path -Parent $PSScriptRoot
$cli = Join-Path $root "tools\tailwindcss.exe"
if (-not (Test-Path $cli)) {
    New-Item -ItemType Directory -Force (Join-Path $root "tools") | Out-Null
    Invoke-WebRequest -Uri "https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-windows-x64.exe" -OutFile $cli
}
& $cli -c (Join-Path $root "tailwind.config.js") `
    -i (Join-Path $root "static\src\input.css") `
    -o (Join-Path $root "static\css\app.css") --minify

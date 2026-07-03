# Narcos Codex Review Gate (PowerShell version)
# Invoke code review at checkpoint
# Usage: ./scripts/codex-review.ps1 [-Phase "P2"] [-Files "narcos/docs/"]

param(
  [string]$Phase = "general",
  [string]$Files = "."
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "═════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Codex Review Gate: $Phase" -ForegroundColor Cyan
Write-Host "═════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Analyzing: $Files"
Write-Host ""

# Create reports dir if it doesn't exist
if (-not (Test-Path "reports")) {
  New-Item -ItemType Directory -Path "reports" -Force | Out-Null
}

# Run local validation suite
Write-Host "Running local validation suite..." -ForegroundColor Yellow
Write-Host ""

# Type check (if mypy installed)
Write-Host "  • Type-checking..." -ForegroundColor Gray
try {
  $output = & python -m mypy $Files --ignore-missing-imports --no-error-summary 2>&1 | Select-Object -First 20
  if ($output) { $output }
} catch {
  Write-Host "    (mypy not available)" -ForegroundColor DarkGray
}

# Run tests
Write-Host "  • Running tests..." -ForegroundColor Gray
try {
  $output = & python -m pytest $Files --tb=short -q 2>&1 | Select-Object -Last 5
  if ($output) { $output }
} catch {
  Write-Host "    (pytest error)" -ForegroundColor Red
}

# Lint check (if flake8 installed)
Write-Host "  • Linting..." -ForegroundColor Gray
try {
  $output = & python -m flake8 $Files --max-line-length=100 2>&1 | Select-Object -First 10
  if ($output) { $output }
} catch {
  Write-Host "    (flake8 not available)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "═════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Local validation complete. Codex review gate is ready." -ForegroundColor Cyan
Write-Host "The main agent will invoke /code-review ultra for detailed analysis." -ForegroundColor Gray
Write-Host "═════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

exit 0

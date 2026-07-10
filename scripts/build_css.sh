#!/usr/bin/env bash
# Linux/dev twin of build_css.ps1: build static/css/app.css from
# static/src/input.css with the same pinned Tailwind version (D55).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
npx --yes tailwindcss@3.4.17 -c tailwind.config.js \
  -i static/src/input.css -o static/css/app.css --minify

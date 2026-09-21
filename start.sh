#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
for item in backend/.venv/bin/python backend/.env frontend/.env frontend/node_modules; do
  if [ ! -e "$item" ]; then echo "Missing $item. Run bash ./setup.sh first."; exit 1; fi
done
command -v node >/dev/null || { echo 'Node.js is missing. Run setup.sh.'; exit 1; }
exec node scripts/launch.mjs dev

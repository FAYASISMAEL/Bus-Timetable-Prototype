#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .runtime/tmp
export TMPDIR="$PWD/.runtime/tmp"
command -v python3 >/dev/null || { echo 'Install Python 3.10+ and python3-venv.'; exit 1; }
python3 -c 'import sys; print(sys.version); sys.exit(0 if sys.version_info >= (3,10) else 1)'
command -v node >/dev/null || { echo 'Install Node.js 20.19+ or 22.12+ from https://nodejs.org/'; exit 1; }
node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22 || a===22&&b>=12 || a===20&&b>=19 ? 0 : 1)'
command -v npm >/dev/null || { echo 'npm is missing. Reinstall Node.js.'; exit 1; }
node --version
npm --version
for directory in backend frontend; do
  if [ ! -f "$directory/.env" ]; then cp "$directory/.env.example" "$directory/.env"; fi
done
if [ ! -x backend/.venv/bin/python ]; then python3 -m venv backend/.venv; fi
source backend/.venv/bin/activate
python -m pip install --no-cache-dir --upgrade pip
python -m pip install --no-cache-dir -r backend/requirements.txt
(
  cd frontend
  npm install --cache ../.runtime/npm-cache
)
case "$(uname -s)" in
  Darwin)
    if command -v brew >/dev/null; then
      echo 'If Tesseract/languages are missing, run: brew install tesseract tesseract-lang'
    else
      echo 'Install Homebrew from https://brew.sh then run: brew install tesseract tesseract-lang'
    fi
    ;;
  Linux)
    if command -v apt-get >/dev/null; then
      echo 'If Tesseract is missing, run: sudo apt-get update && sudo apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-mal'
    else
      echo 'Install Tesseract using your distribution package manager, including eng and mal data.'
    fi
    ;;
  *) echo 'Unsupported automatic OS installation. Install Tesseract manually.' ;;
esac
if ! python scripts/check_environment.py --install-language-data; then
  echo 'Dependencies installed; runtime setup still needs attention. Read the report above and README.md.'
fi
echo 'Start: bash ./start.sh'

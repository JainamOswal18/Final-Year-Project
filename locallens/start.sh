#!/usr/bin/env bash
# One command: install, download models, build the web app, start the server. Safe to run again.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import locallens" 2>/dev/null; then
  echo "Installing Python packages..."
  pip install --quiet --upgrade pip
  pip install --quiet -e ".[dev]"
fi

if [ ! -f models/qwen2.5-0.5b-instruct-q4_k_m.gguf ]; then
  echo "Downloading the models (one time, needs internet)..."
  python scripts/download_model.py
fi

if [ ! -f data/synthetic/orders.csv ]; then python scripts/make_synthetic_data.py; fi

if [ ! -f web/dist/index.html ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "Building the web app..."
    (cd web && npm ci --silent && npm run build --silent)
  else
    echo "Node.js (npm) is needed once to build the web app: https://nodejs.org" >&2
    exit 1
  fi
fi

echo "LocalLens is starting at http://${LOCALLENS_HOST:-127.0.0.1}:${LOCALLENS_PORT:-8000}"
exec python -m locallens.server

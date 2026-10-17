#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo 'Install the Python environment first; see README.md.' >&2
  exit 1
fi
if [[ ! -f frontend/dist/index.html ]]; then
  (cd frontend && npm ci --no-fund --no-audit && npm run build)
fi
echo "Tláloc: http://127.0.0.1:${PORT:-8000} (Ctrl+C to stop)"
exec .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port "${PORT:-8000}" --no-access-log

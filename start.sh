#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [[ ! -f "$VENV/bin/python" ]]; then
  echo "Error: venv not found at $VENV"
  echo "Run: python3.12 -m venv .venv && .venv/bin/pip install -e ."
  exit 1
fi

echo "Starting FastAPI backend on :8001..."
(cd "$SCRIPT_DIR" && "$VENV/bin/uvicorn" api.main:app --port 8001 --reload) &
API_PID=$!

echo "Starting Vite frontend on :5173..."
(cd "$SCRIPT_DIR/ui" && npm run dev) &
UI_PID=$!

trap "kill $API_PID $UI_PID 2>/dev/null; echo 'Stopped.'" EXIT

echo ""
echo "Review UI: http://localhost:5173"
echo "API:       http://localhost:8001"
echo ""

wait

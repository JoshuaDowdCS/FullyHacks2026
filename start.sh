#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
BAR_W=30

_bar() {
  local current=$1 total=$2
  local filled=$(( BAR_W * current / total ))
  local empty=$(( BAR_W - filled ))
  printf '%0.s⣿' $(seq 1 $filled 2>/dev/null) || true
  printf '%0.s⣀' $(seq 1 $empty 2>/dev/null) || true
}

wait_for_port() {
  local port=$1 label=$2 max=$3
  local i=0
  while ! nc -z localhost "$port" 2>/dev/null; do
    i=$(( i + 1 ))
    if (( i > max )); then
      printf "\r  %s  %s  timeout!\n" "$label" "$(_bar 0 $max)"
      return 1
    fi
    printf "\r  %s  %s  waiting..." "$label" "$(_bar $i $max)"
    sleep 0.3
  done
  printf "\r  %s  %s  ready!   \n" "$label" "$(_bar $max $max)"
}

if [[ ! -f "$VENV/bin/python" ]]; then
  echo "Error: venv not found at $VENV"
  echo "Run: python3.12 -m venv .venv && .venv/bin/pip install -e ."
  exit 1
fi

(cd "$SCRIPT_DIR" && "$VENV/bin/uvicorn" api.main:app --port 8001 --reload) &>/dev/null &
API_PID=$!

(cd "$SCRIPT_DIR/ui" && npm run dev) &>/dev/null &
UI_PID=$!

trap "kill $API_PID $UI_PID 2>/dev/null; echo 'Stopped.'" EXIT

echo ""
wait_for_port 8001 "API " 50
wait_for_port 5173 "UI  " 50
echo ""
echo "Review UI: http://localhost:5173"
echo "API:       http://localhost:8001"
echo ""

wait

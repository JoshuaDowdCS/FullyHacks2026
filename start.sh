#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
LOG_DIR="$SCRIPT_DIR/.logs"
BAR_W=30

# Colors
C_API="\033[36m"    # cyan
C_UI="\033[35m"     # magenta
C_OK="\033[32m"     # green
C_ERR="\033[31m"    # red
C_DIM="\033[2m"     # dim
C_BOLD="\033[1m"    # bold
C_RST="\033[0m"     # reset

ts() { date "+%H:%M:%S"; }

log_api() { printf "${C_DIM}[$(ts)]${C_RST} ${C_API}[API]${C_RST} %s\n" "$*"; }
log_ui()  { printf "${C_DIM}[$(ts)]${C_RST} ${C_UI}[UI]${C_RST}  %s\n" "$*"; }
log_ok()  { printf "${C_DIM}[$(ts)]${C_RST} ${C_OK}[OK]${C_RST}  %s\n" "$*"; }
log_err() { printf "${C_DIM}[$(ts)]${C_RST} ${C_ERR}[ERR]${C_RST} %s\n" "$*"; }
log_sys() { printf "${C_DIM}[$(ts)]${C_RST} ${C_BOLD}[SYS]${C_RST} %s\n" "$*"; }

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

# --- Preflight checks ---
echo ""
log_sys "Starting FullyHacks2026 dev environment"
log_sys "Working directory: $SCRIPT_DIR"

if [[ ! -f "$VENV/bin/python" ]]; then
  log_err "venv not found at $VENV"
  log_err "Run: python3.12 -m venv .venv && .venv/bin/pip install -e ."
  exit 1
fi
log_ok "Python venv found: $VENV/bin/python"

PYTHON_VER=$("$VENV/bin/python" --version 2>&1)
log_ok "Python version: $PYTHON_VER"

if ! command -v node &>/dev/null; then
  log_err "Node.js not found on PATH"
  exit 1
fi
log_ok "Node version: $(node --version)"
log_ok "npm version: $(npm --version)"

# --- Create log directory ---
mkdir -p "$LOG_DIR"
API_LOG="$LOG_DIR/api.log"
UI_LOG="$LOG_DIR/ui.log"

# --- Start API server ---
log_api "Starting uvicorn on port 8001 (reload enabled)"
log_api "Log file: $API_LOG"
(cd "$SCRIPT_DIR" && "$VENV/bin/uvicorn" api.main:app --port 8001 --reload 2>&1 \
  | while IFS= read -r line; do
      printf "${C_DIM}[$(ts)]${C_RST} ${C_API}[API]${C_RST} %s\n" "$line"
      echo "$line" >> "$API_LOG"
    done) &
API_PID=$!
log_api "Process started (PID $API_PID)"

# --- Start UI dev server ---
log_ui "Starting Vite dev server"
log_ui "Log file: $UI_LOG"
(cd "$SCRIPT_DIR/ui" && npm run dev 2>&1 \
  | while IFS= read -r line; do
      printf "${C_DIM}[$(ts)]${C_RST} ${C_UI}[UI]${C_RST}  %s\n" "$line"
      echo "$line" >> "$UI_LOG"
    done) &
UI_PID=$!
log_ui "Process started (PID $UI_PID)"

# --- Cleanup trap ---
trap '
  echo ""
  log_sys "Shutting down..."
  kill $API_PID 2>/dev/null && log_api "Stopped (PID $API_PID)"
  kill $UI_PID 2>/dev/null && log_ui "Stopped (PID $UI_PID)"
  log_sys "Done. Logs saved in $LOG_DIR/"
' EXIT

# --- Wait for readiness ---
echo ""
wait_for_port 8001 "API " 50
wait_for_port 5173 "UI  " 50
echo ""
log_ok "Review UI: http://localhost:5173"
log_ok "API:       http://localhost:8001"
log_sys "Logs: $LOG_DIR/"
log_sys "Press Ctrl+C to stop both servers"
echo ""

wait

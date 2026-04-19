#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [[ ! -f "$VENV/bin/python" ]]; then
  echo "Error: venv not found at $VENV — run: python3.12 -m venv .venv && .venv/bin/pip install -e ."
  exit 1
fi

read -rp "What dataset do you want to make? " prompt

if [[ -z "$prompt" ]]; then
  echo "Error: prompt cannot be empty"
  exit 1
fi

"$VENV/bin/python" -m detection_pipeline \
  --prompt "$prompt" \
  --keep-model-cache \
  --upload \
  --expand-query-with-gemini

#!/usr/bin/env bash
set -euo pipefail

# Stop a background SDXL LoRA training run.
#
# Usage:
#   bash PT3-backend/scripts/stop_sdxl_lora_bg.sh
#   bash PT3-backend/scripts/stop_sdxl_lora_bg.sh /path/to/run.pid

DEFAULT_LOG_DIR="${DEFAULT_LOG_DIR:-/root/training/sdxl-lora/logs}"
PID_FILE="${1:-}"

if [[ -z "$PID_FILE" ]]; then
  PID_FILE="$(ls -1t "$DEFAULT_LOG_DIR"/*.pid 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "$PID_FILE" || ! -f "$PID_FILE" ]]; then
  echo "No PID file found. Pass a PID file explicitly or start a run first." >&2
  exit 1
fi

pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -z "$pid" ]]; then
  echo "PID file is empty: $PID_FILE" >&2
  exit 1
fi

if kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  echo "Stopped SDXL LoRA training pid=$pid"
else
  echo "Process is not running (pid=$pid)"
fi

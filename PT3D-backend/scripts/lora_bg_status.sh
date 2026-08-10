#!/usr/bin/env bash
set -euo pipefail

# Show status for a background SDXL LoRA training run.
#
# Usage:
#   bash PT3-backend/scripts/lora_bg_status.sh
#   bash PT3-backend/scripts/lora_bg_status.sh /path/to/run.pid /path/to/run.log

DEFAULT_LOG_DIR="${DEFAULT_LOG_DIR:-/root/training/sdxl-lora/logs}"
PID_FILE="${1:-}"
LOG_FILE="${2:-}"

if [[ -z "$PID_FILE" || -z "$LOG_FILE" ]]; then
  latest_pid="$(ls -1t "$DEFAULT_LOG_DIR"/*.pid 2>/dev/null | head -n 1 || true)"
  latest_log="$(ls -1t "$DEFAULT_LOG_DIR"/*.log 2>/dev/null | head -n 1 || true)"
  PID_FILE="${PID_FILE:-$latest_pid}"
  LOG_FILE="${LOG_FILE:-$latest_log}"
fi

if [[ -z "$PID_FILE" || ! -f "$PID_FILE" ]]; then
  echo "No PID file found. Pass a PID file explicitly or start a run first." >&2
  exit 1
fi

if [[ -z "$LOG_FILE" || ! -f "$LOG_FILE" ]]; then
  echo "No log file found. Pass a log file explicitly or start a run first." >&2
  exit 1
fi

pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -z "$pid" ]]; then
  echo "PID file is empty: $PID_FILE" >&2
  exit 1
fi

if kill -0 "$pid" 2>/dev/null; then
  echo "Status: RUNNING"
else
  echo "Status: NOT RUNNING"
fi

echo "PID: $pid"
echo "PID file: $PID_FILE"
echo "Log file: $LOG_FILE"
echo ""
echo "Last 40 log lines:"
tail -n 40 "$LOG_FILE"

#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/root/lora_gui_restart.log"
PID_FILE="/root/lora_gui.pid"
AUTODL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_SCRIPT="$AUTODL_DIR/start_lora_next.sh"

if [[ ! -x "$START_SCRIPT" ]]; then
  echo "missing executable start script: $START_SCRIPT" >&2
  exit 1
fi

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" || true)"
  if [[ "$OLD_PID" =~ ^[0-9]+$ ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    sleep 2
  fi
fi

nohup "$START_SCRIPT" >> "$LOG_FILE" 2>&1 &
echo "$!" > "$PID_FILE"
echo "LoRA Next GUI restart requested, pid=$(cat "$PID_FILE"), log=$LOG_FILE"

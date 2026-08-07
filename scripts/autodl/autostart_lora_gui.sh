#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/root/lora_gui_autostart.log"
PID_FILE="/root/lora_gui.pid"
AUTODL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_SCRIPT="$AUTODL_DIR/start_lora_next.sh"

if [[ ! -x "$START_SCRIPT" ]]; then
  echo "missing executable start script: $START_SCRIPT" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")"
nohup "$START_SCRIPT" >> "$LOG_FILE" 2>&1 &
echo "$!" > "$PID_FILE"
echo "LoRA Next GUI startup requested, pid=$(cat "$PID_FILE"), log=$LOG_FILE"

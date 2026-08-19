#!/usr/bin/env bash
# Anima LoRA Fast CLI training via TOML (no WebUI).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

CONFIG_FILE="${1:-docs/examples/anima-lora-benchmark-fast.toml}"
if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "[Error] Config not found: ${CONFIG_FILE}" >&2
  echo "Usage: $0 [path/to/config.toml]" >&2
  exit 1
fi

if [[ -x "extensions/anima_lora/.venv/bin/python" ]]; then
  FAST_PY="extensions/anima_lora/.venv/bin/python"
elif [[ -f "extensions/anima_lora/.venv/Scripts/python.exe" ]]; then
  FAST_PY="extensions/anima_lora/.venv/Scripts/python.exe"
else
  echo "[Error] Fast venv missing under extensions/anima_lora/.venv" >&2
  echo "Run: bash scripts/cli/install_anima_fast.sh" >&2
  exit 1
fi

TRAIN_PY="extensions/anima_lora/source/train.py"
if [[ ! -f "${TRAIN_PY}" ]]; then
  echo "[Error] Missing ${TRAIN_PY}" >&2
  exit 1
fi

export HF_HOME="${HF_HOME:-${PROJECT_ROOT}/huggingface}"
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export PYTHONUTF8=1

echo "========================================"
echo "  Anima Fast CLI Train"
echo "  Config: ${CONFIG_FILE}"
echo "========================================"
echo ""

exec "${FAST_PY}" "${TRAIN_PY}" --config_file "${CONFIG_FILE}"

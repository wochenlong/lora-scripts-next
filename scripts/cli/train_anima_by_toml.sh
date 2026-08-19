#!/usr/bin/env bash
# Anima LoRA standard (non-Fast) CLI training via TOML.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

CONFIG_FILE="${1:-docs/examples/anima-lora-benchmark-kohya.toml}"
if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "[Error] Config not found: ${CONFIG_FILE}" >&2
  echo "Usage: $0 [path/to/anima-lora.toml]" >&2
  exit 1
fi

export HF_HOME="${HF_HOME:-${PROJECT_ROOT}/huggingface}"
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export PYTHONUTF8=1

echo "========================================"
echo "  Anima LoRA CLI Train (standard / non-Fast)"
echo "  Config: ${CONFIG_FILE}"
echo "========================================"
echo ""

exec python scripts/dev/anima_train_network.py --config_file "${CONFIG_FILE}"

#!/usr/bin/env bash
# Install Anima LoRA Fast plugin without WebUI.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON=""
if [[ -x "${PROJECT_ROOT}/../python_embeded/python.exe" ]]; then
  PYTHON="${PROJECT_ROOT}/../python_embeded/python.exe"
elif [[ -x "${PROJECT_ROOT}/venv/bin/python" ]]; then
  PYTHON="${PROJECT_ROOT}/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  echo "[Error] Python not found." >&2
  exit 1
fi

# uv is bootstrapped automatically by install_anima_fast.py if missing.

export PYTHONUTF8=1
export PYTHONPATH="${PROJECT_ROOT}"

echo "========================================"
echo "  Anima Fast CLI Install"
echo "  Project: ${PROJECT_ROOT}"
echo "========================================"
echo ""
echo "This installs extensions/anima_lora/ without opening WebUI."
echo "Requires NVIDIA GPU, ~16GB+ VRAM, several GB download."
echo "uv will be installed automatically if it is not found."
echo ""

exec "${PYTHON}" -s "${SCRIPT_DIR}/install_anima_fast.py" "$@"

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
echo "This installs the core trainable dependencies for extensions/anima_lora/."
echo "Masking extras (sam3) are optional and installed on demand, not here."
echo "Requires NVIDIA GPU, ~16GB+ VRAM, several GB download."
echo "uv will be installed automatically if it is not found."
echo "Downloads prefer the HuggingFace mirror; set HF_ENDPOINT to override."
echo ""

exec "${PYTHON}" -s "${SCRIPT_DIR}/install_anima_fast.py" "$@"

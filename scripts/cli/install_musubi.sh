#!/usr/bin/env bash
# Install musubi-tuner plugin without WebUI.
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

# uv is bootstrapped automatically by install_musubi.py if missing.

export PYTHONUTF8=1
export PYTHONPATH="${PROJECT_ROOT}"

echo "========================================"
echo "  musubi-tuner CLI Install"
echo "  Project: ${PROJECT_ROOT}"
echo "========================================"
echo ""
echo "This installs the musubi-tuner plugin into extensions/musubi_tuner/."
echo "Requires musubi-tuner source at vendor/musubi-tuner (or --source-root),"
echo "NVIDIA GPU, several GB download."
echo "uv will be installed automatically if it is not found."
echo "Downloads prefer the HuggingFace mirror; set HF_ENDPOINT to override."
echo ""

exec "${PYTHON}" -s "${SCRIPT_DIR}/install_musubi.py" "$@"

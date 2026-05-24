#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

export HF_HOME="${HF_HOME:-huggingface}"

if [[ -n "${USE_CN_MIRROR:-}" && -z "${HF_ENDPOINT:-}" ]]; then
  export HF_ENDPOINT="https://hf-mirror.com"
fi

if [[ -x "venv/bin/python" ]]; then
  exec "venv/bin/python" -m mikazuki.tagger.cli "$@"
else
  exec python -m mikazuki.tagger.cli "$@"
fi

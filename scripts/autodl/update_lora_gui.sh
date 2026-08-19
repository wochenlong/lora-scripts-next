#!/usr/bin/env bash
set -euo pipefail

AUTODL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$AUTODL_DIR/../.." && pwd)"

source /root/miniconda3/etc/profile.d/conda.sh
conda activate lora-next

if [[ -f /etc/network_turbo ]]; then
  source /etc/network_turbo
fi

cd "$REPO_ROOT"
git pull
python "$AUTODL_DIR/apply_lora_next_anima_defaults.py"
"$AUTODL_DIR/restart_lora_gui.sh"

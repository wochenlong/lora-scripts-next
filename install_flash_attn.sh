#!/bin/bash
# Flash Attention 2 installer for source/venv users (Linux / WSL / AutoDL)

set -e

cd "$(dirname "$0")"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo ""
echo "  ============================================"
echo "   Flash Attention 2 Installer (Linux)"
echo "  ============================================"
echo ""

# Check if already installed
if python -c "import flash_attn; print('OK')" 2>/dev/null; then
    echo "  Flash Attention 2 is already installed."
    exit 0
fi

echo "  Installing flash-attn (building from source, needs CUDA toolkit)..."
echo ""
pip install flash-attn --no-build-isolation
echo ""

if python -c "import flash_attn; print('Flash Attention 2 OK')" 2>/dev/null; then
    echo "  Done! attn_mode will auto-detect as 'flash' for Anima LoRA."
else
    echo "  Install failed. Training will use xformers / PyTorch SDPA instead."
    exit 1
fi

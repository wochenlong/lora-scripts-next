#!/bin/bash
# Clear the uv global cache (~/.cache/uv).
#
# Engine installers (Anima Fast / Musubi / AI Toolkit) use the uv cache by
# default so reinstalls and sibling engines share multi-GB downloads (torch
# etc.). Run this script when you need the disk space back.

set -e

cd "$(dirname "$0")"

echo ""
echo "  ============================================"
echo "   Clear uv download cache (Linux)"
echo "  ============================================"
echo ""

if ! command -v uv >/dev/null 2>&1; then
    echo "  [ERROR] uv not found in PATH."
    echo "  Install uv first (https://docs.astral.sh/uv/), or remove the cache"
    echo "  directory manually: rm -rf ~/.cache/uv"
    echo ""
    exit 1
fi

uv cache info || true
echo ""
echo "  Cleaning..."
uv cache clean
echo ""
echo "  Done. Engine reinstalls will download dependencies again on next install."
echo ""

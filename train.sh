#!/usr/bin/env bash
# Legacy SD/SDXL/Flux LoRA CLI entry.
# Anima standard: bash train_anima_by_toml.sh path/to/anima-lora.toml
# Anima Fast:     bash train_anima_fast_by_toml.sh path/to/anima-fast.toml
case "${1:-}" in
  anima|anima-lora|--anima|fast|anima-fast|--fast)
    cat >&2 <<'EOF'
train.sh is the legacy SD/SDXL/Flux LoRA CLI entry.

Use the dedicated Anima entrypoints instead:
  Anima standard: bash train_anima_by_toml.sh path/to/anima-lora.toml
  Anima Fast:     bash train_anima_fast_by_toml.sh path/to/anima-fast.toml
EOF
    exit 2
    ;;
esac
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/cli/train.sh" "$@"

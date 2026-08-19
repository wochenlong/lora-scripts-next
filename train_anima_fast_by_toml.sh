#!/usr/bin/env bash
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/cli/train_anima_fast_by_toml.sh" "$@"

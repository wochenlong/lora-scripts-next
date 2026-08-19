#!/bin/bash
# 国内镜像启动（等价于 USE_CN_MIRROR=1 run_gui.sh）
export USE_CN_MIRROR=1
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_gui.sh" "$@"

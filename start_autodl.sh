#!/bin/bash
# =============================================================================
# AutoDL 镜像启动入口（稳定契约 — 请勿移动、重命名或删除本文件）
#
# 多个 AutoDL / 云 GPU 镜像在「开机启动」里写死了本路径，例如：
#   bash /root/lora-scripts-next/start_autodl.sh
# 若 git 整理根目录时删掉或挪走此文件，实例将无法正常拉起 WebUI。
#
# 需要改启动逻辑时：只改本文件内容，或让本文件 exec 其他脚本；
# 不要改文件名与仓库根目录相对路径。
#
# 端口：GUI 6006（AutoDL 默认映射）| 训练监控 6008（gui.py 自动拉起）
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")"

export HF_HOME="huggingface"
export PYTHONUTF8=1

exec python gui.py \
  --port 6006 \
  --listen \
  --host 0.0.0.0 \
  --skip-prepare-environment \
  --disable-tensorboard \
  "$@"

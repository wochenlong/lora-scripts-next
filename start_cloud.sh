#!/bin/bash
# =============================================================================
# start_cloud.sh — 云端 slim 装机/直启一体入口
#
# 面向带 torch 的云镜像（AutoDL 等）：检测宿主 python/torch/cuda，按引擎
# pack 的 REQUIRES 匹配并 slim 安装（复用宿主 torch，不建 venv），完成后
# 写 .cloud_install_done；之后启动检测指纹直启，指纹不符直接报错。
#
# 镜像「开机启动」可绑定本路径；一旦绑定，与 start_autodl.sh 一样不可移动/
# 重命名/删除，只能改内容。
#
# 端口：GUI 6006（可用 --port 覆盖）| 训练监控 6008（gui.py 自动拉起）
# 非交互打镜像：bash start_cloud.sh --engine <id> --yes
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif [ -x /usr/bin/python3 ]; then
  PY=/usr/bin/python3
else
  echo "start_cloud: 未找到 python3，无法引导" >&2
  exit 1
fi

exec "$PY" scripts/cloud/bootstrap.py "$@"

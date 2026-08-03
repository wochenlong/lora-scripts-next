#!/bin/bash
# Linux/macOS GUI launcher. China mirrors: USE_CN_MIRROR=1 bash run_gui.sh

export HF_HOME=huggingface
export PYTHONUTF8=1

if [[ "${USE_CN_MIRROR:-}" == "1" ]]; then
  export HF_ENDPOINT=https://hf-mirror.com
  export PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
fi

if [[ -f "./venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "./venv/bin/activate"
else
  echo -e "\033[36m首次运行：正在创建虚拟环境 venv，请稍候...\033[0m"
  if ! command -v python3 >/dev/null 2>&1; then
    echo -e "\033[31m未找到 python3，请先安装 Python 3。\033[0m"
    exit 1
  fi
  python3 -m venv venv
  if [ $? -ne 0 ]; then
    echo -e "\033[31m虚拟环境创建失败，请先安装 venv 支持（如 apt install python3-venv）后重试。\033[0m"
    exit 1
  fi
  # shellcheck source=/dev/null
  source "./venv/bin/activate"
  python -m pip install --upgrade pip
fi

if [ ! -f "vendor/sd-scripts/anima_train_network.py" ]; then
    echo -e "\033[36m首次运行：正在初始化必要组件，请稍候...\033[0m"
    git submodule update --init --recursive
    if [ $? -ne 0 ]; then
        echo -e "\033[31m组件初始化失败，请检查网络连接后重新运行。\033[0m"
        exit 1
    fi
    echo -e "\033[32m初始化完成，继续启动...\033[0m"
fi

python gui.py "$@"

#!/bin/bash
# Linux/macOS GUI launcher. China mirrors: USE_CN_MIRROR=1 bash run_gui.sh

export HF_HOME=huggingface
export PYTHONUTF8=1

if [[ "${USE_CN_MIRROR:-}" == "1" ]]; then
  export HF_ENDPOINT=https://hf-mirror.com
  # 用户已手动指定 PIP_INDEX_URL 时优先，未指定才默认清华镜像
  export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
fi

venv_python_ok() {
  [[ -x "./venv/bin/python" ]] && ./venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3, 10), (3, 11)) else 1)'
}

if [[ -f "./venv/bin/activate" ]] && venv_python_ok; then
  # shellcheck source=/dev/null
  source "./venv/bin/activate"
else
  if [[ -f "./venv/bin/activate" ]]; then
    echo -e "\033[33m检测到 venv 的 Python 版本不是 3.10/3.11（项目依赖无对应预编译包），正在重建...\033[0m"
    rm -rf venv
  else
    echo -e "\033[36m首次运行：正在创建虚拟环境 venv（Python 3.10），请稍候...\033[0m"
  fi
  if ! command -v uv >/dev/null 2>&1; then
    echo -e "\033[36m正在安装 uv ...\033[0m"
    python3 -m pip install --user uv
    if [ $? -ne 0 ]; then
      echo -e "\033[31muv 安装失败，请检查 pip 网络后重试。\033[0m"
      exit 1
    fi
  fi
  # pip --user 安装的 uv 可能不在 PATH 中，此时用 python3 -m uv 调用
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.10 venv
  else
    python3 -m uv venv --python 3.10 venv
  fi
  if [ $? -ne 0 ]; then
    echo -e "\033[31m虚拟环境创建失败，请检查网络后重试。\033[0m"
    exit 1
  fi
  # 不用 uv --seed：seed 包要从 PyPI 镜像下载，镜像异常会失败；ensurepip 用解释器内置 wheel 离线安装 pip
  ./venv/bin/python -m ensurepip --upgrade
  if [ $? -ne 0 ]; then
    echo -e "\033[31mpip 初始化失败，请删除 venv 目录后重试。\033[0m"
    exit 1
  fi
  # shellcheck source=/dev/null
  source "./venv/bin/activate"
  echo -e "\033[36m首次运行：正在安装依赖（可能需要几分钟）...\033[0m"
  deps_installed=
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python ./venv/bin/python -r requirements.txt && deps_installed=1
  else
    python3 -m uv pip install --python ./venv/bin/python -r requirements.txt && deps_installed=1
  fi
  if [ -z "$deps_installed" ]; then
    echo -e "\033[33muv 安装依赖失败（部分 PyPI 镜像会拒绝 uv 的下载请求），改用 pip 重试...\033[0m"
    ./venv/bin/python -m pip install -r requirements.txt
    if [ $? -ne 0 ]; then
      echo -e "\033[31m依赖安装失败，请检查网络后重新运行。\033[0m"
      exit 1
    fi
  fi
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

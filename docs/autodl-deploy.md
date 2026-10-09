# AutoDL 5090 部署 lora-scripts-next 指导

> **注意（2026-09 起）**：训练依赖（PyTorch、sd-scripts 训练栈）已不再装进主环境，改由各训练引擎的独立 venv 承载——启动后在 WebUI「设置 → 训练引擎」页一键安装即可（自带镜像源选择）。本文的手工 torch/训练栈安装步骤仅适合需要自定义训练环境的高级场景，普通用户装 GUI 依赖（`requirements.txt`）后即可启动。

本文用于指导 AutoDL 实例上的 Cursor/Agent 部署 `lora-scripts-next` 训练环境。目标硬件是 RTX 5090 / 50 系显卡，重点是保证 CUDA、PyTorch、Python 与本项目依赖兼容。

## 1. AutoDL 镜像选择

在 AutoDL 创建实例时，优先选择：

- 框架：`PyTorch`
- 框架版本：`2.8.0`
- CUDA 版本：`12.8`
- 系统：`Ubuntu 22.04`

如果 AutoDL 只提供 `Python 3.12` 的 `PyTorch 2.8.0 + CUDA 12.8` 镜像，也可以选择。不要直接用系统 Python 运行本项目，进入实例后单独创建 Python 3.10 conda 环境。

不要选择 CUDA 12.1 / 12.4 / 12.5 镜像。RTX 5090 属于 50 系 Blackwell，训练环境应使用 CUDA 12.8 或更高版本。

## 2. 登录实例后先确认 GPU

```bash
nvidia-smi
```

确认输出里能看到 RTX 5090，并且驱动正常。

## 3. 创建 Python 3.10 环境

本项目 README 要求 Python 3.10，且依赖里包含较旧的训练栈组件，例如 `gradio==3.44.2`、`pytorch-lightning==1.9.0`。因此不要使用镜像自带的 Python 3.12。

```bash
source /root/miniconda3/etc/profile.d/conda.sh

conda create -n lora-next python=3.10 -y \
  -c https://mirrors.ustc.edu.cn/anaconda/pkgs/main \
  -c https://mirrors.ustc.edu.cn/anaconda/pkgs/r \
  --override-channels \
  --solver=classic

conda activate lora-next

which python
python --version
pip install -U pip setuptools wheel
```

期望：

```text
/root/miniconda3/envs/lora-next/bin/python
Python 3.10.x
```

说明：AutoDL 镜像内置的 conda 源可能包含失效的 `pkgs/free` 通道，导致 `conda create` 报 `repository does not start with an object`。上面的命令使用中科大源并通过 `--override-channels` 绕开坏源，已在 AutoDL 实例中验证可创建 `Python 3.10.20` 环境。

## 4. 安装 PyTorch cu128

在 `lora-next` 环境中安装 CUDA 12.8 对应的 PyTorch。

```bash
pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
```

验证：

```bash
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

期望类似：

```text
2.8.0+cu128
12.8
True
NVIDIA GeForce RTX 5090
```

## 5. 获取项目代码

如果实例里还没有代码：

```bash
cd /root
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
```

如果已经上传或同步了项目代码，则进入项目根目录即可：

```bash
cd /root/lora-scripts-next
```

确认当前目录中有：

```bash
ls
```

应能看到 `requirements.txt`、`run_gui.sh`、`mikazuki/`、`scripts/` 等文件。

## 6. 安装项目依赖

确保仍在 `lora-next` 环境中：

```bash
conda activate lora-next
pip install -r requirements.txt
```

如需国内源，可临时使用：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

安装完成后再次验证核心包：

```bash
python -c "import torch, accelerate, diffusers, transformers; print('torch', torch.__version__, torch.version.cuda); print('accelerate', accelerate.__version__); print('diffusers', diffusers.__version__); print('transformers', transformers.__version__)"
```

## 7. 启动 WebUI

### 7.1 镜像开机入口（稳定契约）

若 AutoDL **自定义镜像**或实例模板在「启动命令」里写死了：

```bash
bash /root/lora-scripts-next/start_autodl.sh
```

则仓库根目录的 **`start_autodl.sh` 不得移动、重命名或删除**（仅可修改文件内容）。整理项目根目录时务必保留此路径，否则已发布的云镜像会开机失败。

该脚本会：

- 监听 `0.0.0.0:6006`（与 AutoDL 常用映射一致）
- 调用 `gui.py --skip-prepare-environment --disable-tensorboard`
- 由 `gui.py` 自动拉起训练监控（默认 `6008`）

手动调试时也可直接执行：

```bash
cd /root/lora-scripts-next
bash start_autodl.sh
```

### 7.2 手动 / conda 环境启动

在已激活 `lora-next` 等环境、且希望使用 **28000** 端口时：

```bash
conda activate lora-next
cd /root/lora-scripts-next
bash run_gui.sh --listen
```

或：

```bash
python gui.py --listen --host 0.0.0.0 --port 28000
```

### 7.3 端口对照

| 服务 | 端口 | 说明 |
|------|------|------|
| `start_autodl.sh` WebUI | `6006` | 镜像默认绑定入口 |
| 常规 `run_gui.sh` WebUI | `28000` | 与 Windows 整合包一致 |
| 训练监控 | `6008` | `gui.py` 子进程 |
| TensorBoard | `6006` | 与 7.1 冲突时需 `--disable-tensorboard`（`start_autodl.sh` 已禁用） |

在 AutoDL 控制台里开放或映射对应端口，然后从浏览器访问公网地址。

### 7.4 与 `start_lora_next.sh` 的区别

| 脚本 | 用途 |
|------|------|
| **`start_autodl.sh`** | 薄入口，给**云镜像开机**用；路径不可变 |
| `scripts/autodl/start_lora_next.sh`（根目录同名文件为转发） | 完整链：conda、`apply_lora_next_anima_defaults.py`、清端口；适合已配置 `lora-next` 的运维 |

新做镜像模板时，优先用 **`start_autodl.sh`** 作为开机命令，避免与旧 conda 链耦合。

## 8. 推荐目录规划

如果目标是制作 AutoDL 自定义镜像，项目代码和 Python 环境要放在系统盘 `/root` 下；数据盘 `/root/autodl-tmp` 在打包镜像时不会保留。

建议把项目和环境放在系统盘，把模型、数据集和输出按需要放到数据盘或共享存储。

建议结构：

```text
/root/
  miniconda3/envs/lora-next/
  lora-scripts-next/

/root/autodl-tmp/
  models/
  datasets/
  outputs/
```

训练时在 WebUI 中把模型、数据集、输出路径指向这些目录。

## 9. 常见问题

### 9.1 Python 版本是 3.12

这是基础镜像自带 Python，不要直接使用。重新执行：

```bash
source /root/miniconda3/etc/profile.d/conda.sh

conda create -n lora-next python=3.10 -y \
  -c https://mirrors.ustc.edu.cn/anaconda/pkgs/main \
  -c https://mirrors.ustc.edu.cn/anaconda/pkgs/r \
  --override-channels \
  --solver=classic

conda activate lora-next
```

后续所有安装和启动命令都在 `lora-next` 环境中执行。

### 9.2 `torch.cuda.is_available()` 是 `False`

先检查：

```bash
nvidia-smi
python -c "import torch; print(torch.__version__, torch.version.cuda)"
```

如果 `nvidia-smi` 正常，但 PyTorch 不是 `+cu128`，重新安装：

```bash
pip uninstall -y torch torchvision torchaudio
pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
```

### 9.3 `conda create` 报清华源 / `pkgs/free` 错误

如果出现类似 `repository does not start with an object`，通常是当前 `.condarc` 中的旧 `pkgs/free` 源异常。直接用中科大源覆盖通道创建环境：

```bash
source /root/miniconda3/etc/profile.d/conda.sh

conda create -n lora-next python=3.10 -y \
  -c https://mirrors.ustc.edu.cn/anaconda/pkgs/main \
  -c https://mirrors.ustc.edu.cn/anaconda/pkgs/r \
  --override-channels \
  --solver=classic
```

创建成功后确认：

```bash
conda activate lora-next
which python
python --version
```

### 9.4 `xformers` 报错

5090 上不要为了 `xformers` 降级 CUDA 或 PyTorch。优先先确认不使用 `xformers` 是否能训练；PyTorch 2.x 自带 SDPA，很多训练场景可以不用 `xformers`。

如果确实需要 `xformers`，安装支持当前 PyTorch / CUDA 的版本：

```bash
pip install -U xformers
```

安装后验证：

```bash
python -c "import xformers; print(xformers.__version__)"
```

### 9.5 `bitsandbytes` 报错

项目当前依赖里有 `bitsandbytes==0.46.0`。如果在 5090 上加载失败，可以尝试升级：

```bash
pip install -U bitsandbytes
```

验证：

```bash
python -c "import bitsandbytes as bnb; print(bnb.__version__)"
```

### 9.6 OpenCV / 图形库缺失

如果出现 `libGL.so.1`、`libsm6`、`libxext6` 相关错误：

```bash
apt update
apt install -y ffmpeg libsm6 libxext6 libgl1 python3-tk
```

## 10. 给 Agent 的执行顺序

Agent 在 AutoDL 上部署时按这个顺序执行：

1. 确认 AutoDL 镜像是 `PyTorch 2.8.0 + CUDA 12.8`。
2. 用 `nvidia-smi` 确认 RTX 5090 可见。
3. 用中科大源创建并激活 `conda` 环境：`lora-next / Python 3.10`。
4. 安装 `torch==2.8.0` 的 `cu128` wheel。
5. 克隆或进入系统盘 `/root/lora-scripts-next` 项目目录。
6. 执行 `pip install -r requirements.txt`。
7. 用 Python 命令验证 `torch.cuda.is_available()`、CUDA 版本和 GPU 名称。
8. 启动 `bash run_gui.sh --listen` 或 `python gui.py --listen --host 0.0.0.0 --port 28000`。
9. 如遇 `xformers` / `bitsandbytes` 问题，优先升级对应包，不要降级 CUDA。

## 11. 最小可复制命令

以下命令适合在一个全新的 AutoDL 实例上执行：

```bash
nvidia-smi

source /root/miniconda3/etc/profile.d/conda.sh

conda create -n lora-next python=3.10 -y \
  -c https://mirrors.ustc.edu.cn/anaconda/pkgs/main \
  -c https://mirrors.ustc.edu.cn/anaconda/pkgs/r \
  --override-channels \
  --solver=classic

conda activate lora-next

pip install -U pip setuptools wheel
pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128

cd /root
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next

pip install -r requirements.txt

python -c "import sys, torch; print(sys.version); print(torch.__version__, torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"

bash run_gui.sh --listen
```


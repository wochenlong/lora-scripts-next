<p align="center">
  <img src="assets/readme/anima-cover.png" alt="lora-scripts-next · Anima Trainer" width="880" />
</p>

<h1 align="center">lora-scripts-next</h1>

<p align="center">
  <strong>SD-Trainer</strong> — LoRA 一键训练 GUI，支持 SD / SDXL / Flux / <b>Anima</b><br/>
  <sub>基于 <a href="https://github.com/kohya-ss/sd-scripts">kohya-ss/sd-scripts</a> 后端，秋叶系界面体验。</sub>
</p>

<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next"><img src="https://img.shields.io/github/stars/wochenlong/lora-scripts-next?style=flat-square&label=stars&logo=github&color=8b5cf6" alt="stars"/></a>
  <a href="https://github.com/wochenlong/lora-scripts-next"><img src="https://img.shields.io/github/forks/wochenlong/lora-scripts-next?style=flat-square&label=forks&color=06b6d4" alt="forks"/></a>
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/main/LICENSE"><img src="https://img.shields.io/github/license/wochenlong/lora-scripts-next?style=flat-square&color=ec4899" alt="license"/></a>
  <a href="https://github.com/wochenlong/lora-scripts-next/releases"><img src="https://img.shields.io/github/v/release/wochenlong/lora-scripts-next?include_prereleases&style=flat-square&color=a78bfa" alt="release"/></a>
</p>

<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next/releases"><b>下载整合包</b></a>
  &nbsp;·&nbsp;
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/main/README.md"><b>English</b></a>
  &nbsp;·&nbsp;
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/main/NOTICE.md"><b>致谢 & 许可</b></a>
</p>

---

## 快速开始

### Windows 整合包（推荐小白用户）

从 [Releases](https://github.com/wochenlong/lora-scripts-next/releases) 下载 **`SD-Trainer-v2.4.0.7z`**（~55 MB，含嵌入式 Python），解压后双击 `run_gui.bat` 即可启动。

首次启动会自动安装 PyTorch + CUDA + 所有依赖（~3 GB 下载），国内用户自动走阿里云/清华镜像加速。

| 文件 | 用途 |
|------|------|
| `run_gui.bat` | 整合包启动入口（内部转到 `run_gui_portable.bat`） |
| `Update-SD-Trainer.bat` | 从 GitHub 拉取最新代码 |
| `Download-Anima-Model.bat` | 从 ModelScope 下载 Anima 基础模型 |

> **系统要求：** Windows 10/11 64 位，NVIDIA 显卡（RTX 20 系列以上），~7 GB 硬盘空间。

#### Anima LoRA 训练显存参考（1024 分辨率，实测）

以下数据来自 RTX 4090 真实基准测试，batch=1，bf16，标准 LoRA（dim=16）：

| 显存 | 可用配置 | 备注 |
|------|----------|------|
| **≥ 24 GB** | 默认参数，1024 分辨率，无需任何节省选项 | 最省心 |
| **≥ 16 GB** | 开启梯度检查点（`gradient_checkpointing`） | 推荐日常使用 |
| **≥ 12 GB** | 梯度检查点，峰值约 12.3 GB | 稳定 |
| **≥ 10 GB** | 梯度检查点 + `blocks_to_swap = 16` | 稳定，速度略降 |
| **≥ 8 GB** | 梯度检查点 + `blocks_to_swap = 24` + `cache_text_encoder_outputs` + LoKr 网络 | 可运行，极限，偶发 OOM 风险 |

> 512 分辨率约节省 2～3 GB；降低 `network_dim`（如 8）也能少量减少显存。

#### 整合包 Flash Attention 2 支持

| 点 | 说明 |
|----|------|
| **flash-attn 依赖 triton** | 预编译的 `flash-attn` wheel 能装进环境，但运行时大量算子仍通过 `flash_attn.ops.triton` 调用 **Triton** 生成的 CUDA kernel。 |
| **嵌入式 Python + triton** | 整合包使用 Python Embeddable（`python_embeded\`），因此固定安装 `triton-windows<3.4` 与匹配 PyTorch 2.7/CUDA 12.8 的 Flash Attention 2 wheel。 |
| **先自检再启用** | 首次安装和 `install_flash_attn.bat` 都会验证 `import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary`。 |
| **失败回退** | 若自检失败，启动时会自动卸载不完整的 flash-attn / triton 组合，训练回退到 **xformers** 或 **PyTorch SDPA**。 |

自检通过后，Anima / SD3 LoRA 会自动选择 `attn_mode=flash`；失败时日志会说明原因并继续训练。

### 从源码安装

```sh
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
```

| 系统 | 操作 |
|------|------|
| Windows | 双击 **`run_gui.bat`**（源码入口，内部转到 `run_gui_source.bat`） |
| Linux | `bash install.bash && bash run_gui.sh` |

启动后浏览器自动打开 **http://127.0.0.1:28000**。

> **Python 版本：** 推荐 **3.10**（所有依赖完美兼容）。3.11–3.12 基本可用，3.13+ 不支持。

#### 常见问题：无法运行 `run_gui.ps1` / 未数字签名

这是 **Windows PowerShell 执行策略** 限制，不是程序坏了。默认策略会拒绝运行未签名的 `.ps1` 脚本。

| 做法 | 说明 |
|------|------|
| **推荐** | 双击 **`run_gui.bat`**（自动转到源码/整合包对应启动器），不要直接运行 `run_gui.ps1` |
| 临时绕过 | 在 PowerShell 中：`powershell -ExecutionPolicy Bypass -File .\run_gui.ps1` |
| 长期放宽（可选） | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`（仅影响当前用户） |

解压后若路径出现 `...\lora-scripts-next-2.4.0\lora-scripts-next-2.4.0\`，说明多解压了一层，请进入**内层**含 `run_gui.bat` 的目录再启动。

#### 指定浏览器

默认使用系统浏览器。可通过 `--browser` 参数指定：

```sh
python gui.py --browser chrome
python gui.py --browser edge
```

#### Flash Attention 2（源码 / venv 用户）

整合包用户可通过首次启动或 `install_flash_attn.bat` 使用同一套固定组合；源码用户也可按下方命令手动安装。

本节适用于：`git clone` 后使用 **`venv`**（或 `python\` 目录下的完整 Python），且已安装 **PyTorch 2.7.0 + CUDA 12.8** 的源码用户。

##### 作用范围

| 训练类型 | Flash Attention 2 |
|----------|---------------------|
| **Anima / SD3 LoRA** | 安装成功且自检通过后，GUI 会自动将 `attn_mode` 设为 `flash`（日志：`Anima attn_mode auto-detected: flash`） |
| **SD 1.5 / SDXL / Flux 等** | 主要使用 **xformers**（`requirements.txt` 已包含）；不依赖 flash-attn wheel |

后端优先级（Anima）：`flash` → `xformers` → `torch`（PyTorch SDPA）。

##### 环境要求

- **Python 3.10**（推荐；3.11–3.12 若存在对应预编译 wheel 也可尝试）
- **64 位** 自建 `venv`，**不要**使用整合包内的 `python_embeded`
- **PyTorch / CUDA** 须与 wheel 匹配：`torch==2.7.0+cu128`、`torchvision==0.22.0+cu128`
- **Windows** 须同时安装 **`triton-windows`** 与 **`flash-attn`**（flash-attn 运行时依赖 Triton kernel）

##### 方式一：自动安装（推荐）

1. 克隆仓库并进入目录，首次运行 **`run_gui.bat`** 或 **`run_gui_source.bat`**（会执行 `install-cn.ps1` 或 `install.ps1` 创建 venv、安装依赖，并尝试安装 flash-attn wheel）。
2. 之后每次源码启动时，`run_gui_source.ps1` 会检测 `triton` + `flash_attn` 是否可用；若缺失，会先装 `triton-windows`，再装预编译 wheel（失败则回退到 xformers / SDPA，不影响训练）。

国内用户首次安装依赖可用：

```powershell
powershell -ExecutionPolicy Bypass -File .\install-cn.ps1
```

国际用户：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

##### 方式二：手动安装（Windows）

在**已激活的 venv** 中执行（版本须与项目一致）：

```powershell
.\venv\Scripts\activate

# 1. PyTorch（若尚未安装）
pip install torch==2.7.0+cu128 torchvision==0.22.0+cu128 --index-url https://download.pytorch.org/whl/cu128

# 2. Triton（Windows 必装，且须先于 flash-attn）
pip install "triton-windows<3.4"

# 3. Flash Attention 2 预编译 wheel（Python 3.10 示例）
pip install https://huggingface.co/lldacing/flash-attention-windows-wheel/resolve/main/flash_attn-2.7.4.post1%2Bcu128torch2.7.0cxx11abiFALSE-cp310-cp310-win_amd64.whl
# 国内镜像（将 cp310 改为 cp311 / cp312 若你使用对应 Python 版本）
pip install https://hf-mirror.com/lldacing/flash-attention-windows-wheel/resolve/main/flash_attn-2.7.4.post1%2Bcu128torch2.7.0cxx11abiFALSE-cp310-cp310-win_amd64.whl
```

##### 方式三：Linux / WSL / AutoDL

```bash
bash install.bash    # 创建 venv、安装 torch/xformers/requirements，并尝试 pip install flash-attn --no-build-isolation
bash run_gui.sh
```

从源码编译 flash-attn 需要 CUDA 工具链与 C++ 编译器；失败时仍会使用 xformers / SDPA。

##### 验证是否安装成功

在**同一 venv** 中运行：

```bash
python -c "import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary; print('Flash Attention 2 OK')"
```

无报错即表示栈完整。然后启动 `python gui.py`，训练 **Anima LoRA** 时在控制台或日志中应看到 `attn_mode` 为 `flash`。

##### 常见问题

| 现象 | 处理 |
|------|------|
| `No module named 'triton'` | 先 `pip install "triton-windows<3.4"`（Windows），再装 flash-attn wheel |
| wheel 安装成功但训练仍用 xformers | 运行上方验证命令；若失败说明 triton 与 flash-attn 未配对，勿只保留 flash-attn |
| `pip install flash-attn` 编译很久或失败 | Windows 请改用 **预编译 wheel**（上表 URL），不要在本机编译 |
| PyTorch 版本不是 2.7+cu128 | wheel 与 CUDA 标签不匹配，请对齐 `install.ps1` 中的 torch 版本后再装 flash-attn |
| 整合包自检失败 | 更新显卡驱动或依赖后重新运行 `install_flash_attn.bat`；损坏组合会在启动时自动清理 |

---

## 功能亮点

- **多模型支持** — SD 1.5 / SDXL / Flux / **Anima** 全部开箱即用
- **Anima LoRA 训练** — 侧边栏一键进入，支持 LoRA / LoKr（LyCORIS）/ **T-LoRA**
- **Attention 加速** — 自动选择后端：源码/venv、整合包、Docker 均在自检通过时优先 Flash Attention 2，失败时回退到 xformers / PyTorch SDPA
- **T-LoRA** — 基于扩散时间步的动态 Rank LoRA，正交初始化，防止过拟合（[论文](https://github.com/ControlGenAI/T-LoRA)）
- **训练监控页** — 随 GUI 自动启动，展示 TensorBoard 同源 Loss / LR 曲线、关键训练参数速查、实时进度、终端日志同步和预览图
- **TensorBoard 内置** — 侧边栏直接查看，无需额外操作
- **显卡检测** — 首次安装自动检测 NVIDIA / AMD 显卡，AMD 用户会收到友好提示及 ROCm 方案指引
- **AutoDL 适配** — 提供专用启动脚本 `start_autodl.sh`

---

## 界面预览

<p align="center">
  <img src="assets/readme/train-monitor-loss.png" alt="训练监控 Loss 曲线" width="920" />
</p>

<p align="center"><sub>6008 训练监控页中的 TensorBoard 同源 Loss / LR 四宫格曲线</sub></p>

<p align="center">
  <img src="assets/readme/train-monitor-samples.png" alt="训练监控预览图" width="920" />
</p>

<p align="center"><sub>训练预览图会直接同步到监控页</sub></p>

<p align="center">
  <img src="assets/readme/train-monitor-logs.png" alt="训练日志查看" width="920" />
</p>

<p align="center"><sub>训练日志同时显示在 CMD 终端与监控页</sub></p>

---

## 详细文档

| 主题 | 链接 |
|------|------|
| Anima LoRA 训练指南 | [docs/anima-training.md](docs/anima-training.md) |
| 训练监控 & SSE 接口 | [docs/train-monitor.md](docs/train-monitor.md) |
| 前端定制 | [docs/frontend-customization.md](docs/frontend-customization.md) |
| Docker 部署 | [docs/docker.md](docs/docker.md) |
| 程序参数一览 | [docs/cli-args.md](docs/cli-args.md) |

---

<details>
<summary><b>更新日志</b></summary>

| 日期 | 内容 |
|------|------|
| 2026-05-21 | **v2.4.0** — 训练稳定性：环境隔离（`PYTHONNOUSERSITE`）、NaN 参数过滤、采样保护、attn_mode 自动降级；整合包：tkinter 支持、`install_xformers.bat` 一键安装 |
| 2026-05-20 | **v2.3.0** — 训练监控体验升级：TensorBoard 同源 Loss/LR 四宫格、关键参数速查、端口冲突自动回退、终端日志同步、后台轮询日志静默 |
| 2026-05-19 | **v2.2.0** — 整合包 flash-attn/triton 治本、run_gui.bat 执行策略与闪退日志、跨盘训练监控、品牌/logo、CONTRIBUTORS.md |
| 2026-05-19 | **v2.1.0** — Flash Attention 2 Windows 预编译 wheel（无需 C++ 编译器）、按步数保存模型、修复 LoKr conv_dim/conv_alpha 传入 undefined 的 bug |
| 2026-05-18 | **v2.0.0** — 整合包发布、Flash Attention 2 自动加速、AMD 显卡检测、自动修复 bf16/fp16 精度问题、`--browser chrome/edge` 指定浏览器、移除子模块改为直接包含 sd-scripts、启动时自动检查更新 |
| 2026-05-18 | T-LoRA 训练支持、交互式 Loss 图表、LoKr 标准化、Windows 便携包、AutoDL 脚本 |
| 2026-05-17 | Anima 训练后端完全迁移至 kohya-ss/sd-scripts |
| 2026-05-06 | 训练监控页重构：实时 Loss 卡片 + 粘性滚动 |

</details>

<details>
<summary><b>致谢 & 上游</b></summary>

| 项目 | 角色 |
|------|------|
| [Akegarasu/lora-scripts](https://github.com/Akegarasu/lora-scripts) | GUI 框架与一键训练体验（"秋叶式"） |
| [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) | 核心训练后端 |
| [KohakuBlueleaf/LyCORIS](https://github.com/KohakuBlueleaf/LyCORIS) | LoKr / LoHa 网络模块（Apache-2.0） |
| [ControlGenAI/T-LoRA](https://github.com/ControlGenAI/T-LoRA) | 时间步动态 LoRA（MIT, AIRI） |
| [bluvoll/Akegarasu-lora-scripts-RF](https://github.com/bluvoll/Akegarasu-lora-scripts-RF) | SDXL Rectified Flow 参考 |

完整归属见 [`NOTICE.md`](NOTICE.md)。

</details>

---

## 贡献者

详见 [**CONTRIBUTORS.md**](CONTRIBUTORS.md)。

---

<p align="center"><sub>维护者：<b>@wochenlong</b></sub></p>

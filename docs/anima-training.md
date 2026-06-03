# Anima LoRA 训练指南

## 进入训练页面

启动 WebUI 后，左侧 sidebar 点 **Anima LoRA** 进入。

> 技术细节：该页面复用了原 SD3 的 URL 槽位（`/lora/sd3.html`），但参数集合与训练脚本已完全是 Anima。

## 模型路径

表单里需要填以下模型路径：

| 字段 | 含义 |
|------|------|
| `pretrained_model_name_or_path` | Anima DiT 主权重，如 `./sd-models/anima/anima-base-v1.0.safetensors` |
| `vae` | Qwen Image VAE 模型路径（必填） |
| `qwen3` | Qwen3 文本模型，可填 `.safetensors` / `.pt` 文件，或完整本地模型目录 |
| `t5` | T5 文本编码器权重 |

## 训练类型

- **LoRA** — 默认训练类型，适合大多数场景
- **LoKr** — 使用 LyCORIS 后端（`lycoris.kohya` + `algo=lokr`），支持 CP 分解、DoRA 等高级参数
- **T-LoRA** — 时间步动态 LoRA，根据扩散时间步自动调整 rank，配合正交初始化防止过拟合（详见下方教程）

## 预览图生成

打开表单里的 **`enable_preview`** 开关后，采样会切到 Anima 推荐参数：
- 分辨率：1024×1024
- CFG：4.5
- 步数：40
- Seed：42
- 自动填入 Anima 风格的正反向提示词

## 图像编辑 / 条件训练（实验）

> **WebUI 入口（推荐）**：侧栏 **「Anima 图像编辑」** → http://127.0.0.1:28000/lora/anima-edit.html（`anima-edit-lora`）。文生图 LoRA 请用 **「Anima」** 页，不要与 Edit 混用。  
> **命令行入口**：[docs/anima-edit-cli.md](anima-edit-cli.md)（单/双参考、`accelerate launch`、双参考数据集字段）。  
> **分支**：`git checkout anima-edit`；Release 整合包与 `main` 暂无本后端。  
> **分支首页速查**：[README-zh.md](../README-zh.md)（WebUI 步骤 + CLI 双参考命令）。

`anima-edit` 分支除专用 Edit 页外，旧版 **Anima LoRA 页内的「图像编辑（实验功能）」** 分组仍可用；新用户请优先使用 **Anima 图像编辑** 专用页（支持 **单张 / 双张参考图** 布局与 manifest 预览）。

条件训练使用成对图片：

| 字段 | 含义 |
|------|------|
| `target_data_dir` | 目标图目录（Target）。放置希望模型学习生成的目标图片，以及同名 `.txt` / `.json` 标签 |
| `conditioning_data_dir` | 参考图目录（Reference / Conditioning）。放置输入参考图，文件名和尺寸需与目标图一致 |
| `conditioning` | 开启图像编辑 / 条件训练模式 |

目录结构示例：

```text
dataset_root/
├── ref/
│   ├── imageA.jpg
│   └── imageB.jpg
└── target/
    ├── imageA.jpg
    ├── imageA.txt
    ├── imageB.jpg
    └── imageB.txt
```

图像编辑预览是普通训练预览的一个切换模式：

- 宽高、CFG、采样步数、采样器、预览频率复用 **训练预览图设置**。
- 开启 `enable_conditioning_preview` 后，普通预览 Prompt 会被 `conditioning_preview_prompt` 替代。
- `sample_conditioning_image` 可指定固定 Control Image。
- `random_conditioning_preview_image` 开启后，可通过 `sample_conditioning_image_data_dir` 每次从目录随机抽取 Control Image。

### 快速训练教学

1. 准备 Target / Reference 两个目录，同名图片一一配对，且图片尺寸必须一致。标签文件放在 Target 目录，例如 `imageA.txt`。
2. 在 **Anima LoRA** 页面填好 Anima 主模型、VAE、Qwen3、T5 等基础模型路径。
3. 打开 **图像编辑（实验功能）**，填写 `target_data_dir` 和 `conditioning_data_dir`。开启后普通 `train_data_dir` 不再作为主数据入口。
4. 打开训练预览，并按需要启用 **图像编辑预览**：固定 `sample_conditioning_image`，或用 `sample_conditioning_image_data_dir` 随机抽参考图。
5. 直接开始训练。WebUI 会自动生成带 `conditioning_data_dir` 的 `dataset_config.toml`，自动启用 latent / text encoder 缓存，并关闭 `sample_at_first`，避免 step 0 噪声预览误导判断。
6. 建议训练若干 epoch 后再看预览图。小数据集可以先用较低学习率和较短 epoch 试跑，观察是否出现黑块、结构偏移等过拟合迹象。

参考配置：[`docs/examples/anima-edit-reference.toml`](examples/anima-edit-reference.toml)。这是基于一次真实 50 epoch 图像编辑训练探针脱敏后的 TOML，已去掉本机路径和数据集名称，可作为参数参考；使用前请替换模型、数据集、输出目录和预览 prompt 路径。

### 单图参考（文档例图 / 门面集）

**布局**：`reference/<stem>.png` 与 `target/<stem>.png` 同名配对（**不要**用 `reference/<stem>/` 子目录）。

```bash
python script/ops/build_anima_edit_single_ref_showcase.py --limit 32
python script/ops/generate_anima_edit_sample_prompts.py ^
  --data-dir data/anima-edit-single-showcase ^
  --out docs/examples/anima-edit-single-ref-sample-prompts.toml ^
  --stems sample0000 sample0010 sample0020
```

| 路径 | 用途 |
|------|------|
| `data/anima-edit-single-showcase/` | 32 对展示训练集（可由 ImagePulse 双参考集取 `1.png` 转成单参考） |
| `docs/examples/anima-edit-single-ref-12epoch.toml` | 12 epoch 训练示例（512，预览与训练 caption 一致） |
| `docs/examples/anima-edit-single-ref-sample-prompts.toml` | 3 条 hero 预览（完整 `target/*.txt`） |
| `docs/assets/anima-edit-single-ref/` | 发布用例图（ref / GT / 推理结果） |

预览务必使用 **与训练相同的完整 caption**；不要用一句泛化英文。训练监控里的曲线图适合调试，正式文档请用上述 hero 三联图。

### 双参考图（方案 2，P0）

支持 **1 目标 + 2 参考**：`reference/<target_stem>/` 子目录内按文件名排序取前 2 张，训练时沿 latent 时间维拼接（`T=3`）。WebUI 选择「双张参考图」布局。

**命令行**：见 **[docs/anima-edit-cli.md](anima-edit-cli.md)** §3（`conditioning_multi_reference = true`、`conditioning_reference_count = 2`、manifest 预览）。示例 TOML：`anima-edit-dual-ref-dataset.toml`、`anima-edit-dual-ref-smoke.toml`、`anima-edit-dual-ref-10epoch.toml`。

设计说明：[docs/design/anima-edit-multi-reference.md](design/anima-edit-multi-reference.md)。显存与分辨率：[docs/design/anima-edit-vram-resolution.md](design/anima-edit-vram-resolution.md)。

### 图像编辑独立训练类型（`anima-edit-lora`）

入口：侧栏 **Anima 图像编辑** → `/lora/anima-edit.html`。Schema：`mikazuki/schema/anima-edit-lora.ts`。

- **训练**：固定双参考（`reference/<stem>/` 下 2 张图），P0 默认分辨率 **512×512**。
- **预览**：仅 **方案 B manifest**（`sample-prompts.toml`），不再使用 `--cn` 单图。
- **自动生成**：开预览且未填 `prompt_file` 时，写入 `config/autosave/*-sample-prompts.toml`；可用「额外预览 Prompt」一行一条生成多条 `[[prompts]]`。
- **手写 manifest**：在预览区填写 `prompt_file` 指向已有 TOML（见下方示例）。

预览 manifest 示例：

- 单条：[docs/examples/anima-edit-sample-prompts.toml](examples/anima-edit-sample-prompts.toml)
- 多条：[docs/examples/anima-edit-sample-prompts-multi.toml](examples/anima-edit-sample-prompts-multi.toml)

训练监控会展示 **参考图1 / 参考图2**（来自 manifest 或自动生成 metadata）。

CLI 验证配置：`anima-edit-dual-ref-smoke.toml`（2 step）、`anima-edit-dual-ref-10epoch.toml`（10 epoch）、`anima-edit-dual-ref-multi-preview.toml`（多 `[[prompts]]` 预览）。

### 外部数据集选型（几十对规模）

魔搭/SEED 全量 Part1（约 350 万对）过大，建议 **HF 上按条数可控** 的数据集，再抽 30–80 对转成 `target/` + `reference/<stem>/`：

| 数据集 | 规模 | 双参考适配 | 说明 |
|--------|------|------------|------|
| [BryanW/HumanEdit](https://huggingface.co/datasets/BryanW/HumanEdit) | ~5.7k 对 | 单参考为主 | 质量高、带 mask；`INPUT`→`reference/1.png`，`OUTPUT`→`target`，第二张可用 `MASK` 或同源裁剪 |
| [osunlp/MagicBrush](https://huggingface.co/datasets/osunlp/MagicBrush) | ~8.8k train | 单参考 | 经典指令编辑；`source_img`→ref1，`target_img`→target，ref2 可用 `mask_img` 或 source 副本 |
| [ONE-Lab/MultiRef-benchmark](https://huggingface.co/datasets/ONE-Lab/MultiRef-benchmark) | 1990（评测） | **天然多图** | `real_world` 子集常含 2+ 输入图 + 合成结果，最接近 P0 双参考协议 |
| [ONE-Lab/MultiRef-dataset](https://huggingface.co/datasets/ONE-Lab/MultiRef-dataset) | 38k 合成 | **多参考** | 可只下 JSONL + 按需拉 `input_images`，抽几十条即可 |
| [AILab-CVC/SEED-Data-Edit-Part2-3](https://huggingface.co/datasets/AILab-CVC/SEED-Data-Edit-Part2-3) Part2 | ~52k | 单参考 | 比 Part1 小很多，适合随机抽子集 |

**推荐优先试**：`MultiRef-benchmark` 的 `real_world`（多输入图）或 `HumanEdit` 抽 50 对（质量稳定）。

**ImagePulseV2-Edit-Merge（本地分片，含 merged 成品图）**：

```bash
python script/ops/import_imagepulsev2_local.py ^
  --src "C:\path\to\1775727894710656047"
```

输出 `data/imagepulsev2-edit-merge-171/`；`mergedimage` → `target/`，`seperated image` 前 2 张 → `reference/`。训练示例：`anima-edit-imagepulse-10epoch.toml`（冒烟）、`anima-edit-imagepulse-30epoch.toml`（推荐）；CLI 预览 manifest：`anima-edit-imagepulse-sample-prompts.toml`（`width`/`height` 与训练分辨率独立，可 512 训 + 1024 预览）。

**一键拉取（真双参考，benchmark real_world）**：

```bash
python script/ops/fetch_multiref_anima_edit_subset.py --count 48 --seed 42
```

输出 `data/anima-edit-multiref-48/` + `docs/examples/anima-edit-multiref-dataset.toml`。HF 版 benchmark **未含 PS 成品图**，`target/` 为 prompt 中的编辑画布（见输出目录 `README-data-limitation.md`）；监督质量训练可用 `--source dataset`。10 epoch 示例：`docs/examples/anima-edit-multiref-10epoch.toml`。

```toml
[[prompts]]
prompt = "..."
negative_prompt = "..."
width = 512
height = 512
references = ["./data/edit3/reference/sample1/1.png", "./data/edit3/reference/sample1/2.png"]
# 或 reference_dir = "./data/edit3/reference/sample1"
```

### 实验限制与质量预期

Anima Edit 当前是 **Anima 文生图基座 + conditioning LoRA** 的实验训练链路，不等同于 Qwen Image Edit 这类专门的图像编辑模型。专用编辑模型通常经过大规模编辑对、局部一致性和指令保持训练；本分支更适合验证特定 paired dataset 的映射能力，局部边界和复杂遮挡的稳定性会弱一些。

如果同一位置在后续 epoch 里反复出现黑块、污渍、错误色块或结构漂移，通常说明 LoRA 开始把小数据集里的局部错误学进去。可优先尝试：

- 选择更早的 checkpoint，例如预览图开始变脏之前的 epoch。
- 将 `unet_lr` 从 `5e-5` 降到 `2e-5` / `3e-5`。
- 降低 `network_dim` 或减少总 epoch。
- 增加更干净、更多样的 Target / Reference 配对图，减少单一构图导致的固定伪影。

<p align="center">
  <img src="../assets/readme/anima-edit-limitations.png" alt="Anima Edit 过拟合伪影示例" width="920" />
</p>

<p align="center"><sub>示例：小数据集在有效学习后继续训练，局部色块伪影会逐渐固定，通常应回退到更早 checkpoint。</sub></p>

### 命令行 / TOML 训练

如果你不想通过 WebUI 表单启动，也可以直接使用本仓库的 sd-scripts 入口跑 Anima Edit。参考文件：

- 主训练配置：[`docs/examples/anima-edit-reference.toml`](examples/anima-edit-reference.toml)
- 数据集配置：[`docs/examples/anima-edit-dataset.toml`](examples/anima-edit-dataset.toml)
- 预览 prompt：[`docs/examples/anima-edit-sample-prompts.txt`](examples/anima-edit-sample-prompts.txt)

1. 准备成对数据集：

```text
data/anima-edit/
├── reference/
│   ├── imageA.png
│   └── imageB.png
└── target/
    ├── imageA.png
    ├── imageA.txt
    ├── imageB.png
    └── imageB.txt
```

`reference/` 与 `target/` 中的图片必须同名、同尺寸；标签文件放在 `target/` 目录。

2. 修改 `docs/examples/anima-edit-dataset.toml`：

```toml
[general]
resolution = "1024,1024"
caption_extension = ".txt"
enable_bucket = true
bucket_reso_steps = 64

[[datasets]]
num_repeats = 1

[[datasets.subsets]]
image_dir = "./data/anima-edit/target"
conditioning_data_dir = "./data/anima-edit/reference"
```

`conditioning_data_dir` 是参考图目录，`image_dir` 是目标图目录。

3. 修改 `docs/examples/anima-edit-reference.toml` 里的模型路径、输出目录和训练参数。关键项如下：

```toml
pretrained_model_name_or_path = "./sd-models/anima/anima-base-v1.0.safetensors"
vae = "./sd-models/anima/qwen_image_vae.safetensors"
qwen3 = "./sd-models/anima/qwen_3_06b_base.safetensors"
dataset_config = "./docs/examples/anima-edit-dataset.toml"

conditioning = true
network_module = "networks.lora_anima"
network_train_unet_only = true

cache_latents = true
cache_text_encoder_outputs = true
sample_at_first = false
sample_prompts = "./docs/examples/anima-edit-sample-prompts.txt"
```

条件训练依赖缓存后的 Target / Reference latents，建议保留 `cache_latents = true` 和 `cache_text_encoder_outputs = true`。`sample_at_first = false` 用来避免 step 0 的噪声预览误导判断。

4. 修改 `docs/examples/anima-edit-sample-prompts.txt`：

```text
high quality Anima style illustration, clean color, detailed character --n low quality, blurry, noisy, bad anatomy --w 1024 --h 1024 --l 4.5 --s 40 --cn ./data/anima-edit/reference/imageA.png
```

`--cn` 后面填写 Control Image / 参考图路径，路径不要加双引号。训练时看到日志中出现 `loading controlnet image`，说明预览图正在使用参考图。

5. 启动训练：

```powershell
accelerate launch --num_cpu_threads_per_process 1 scripts/dev/anima_train_network.py --config_file docs/examples/anima-edit-reference.toml
```

如果你已经在 `vendor/sd-scripts` 目录内直接运行，也可以改为调用该目录下的 `anima_train_network.py`。本仓库推荐使用 `scripts/dev/anima_train_network.py`，它会适配 WebUI/仓库内的 Anima 后端约定。

### 推理使用

训练得到的 LoRA 可以在 ComfyUI 中配合 [Mirumo0u0/ComfyUI-Cosmos-Reference](https://github.com/Mirumo0u0/ComfyUI-Cosmos-Reference) 节点使用。该节点为 Cosmos 及其衍生模型（包括 Anima）添加参考图输入能力，适合作为 Anima Edit LoRA 的推理入口。

<p align="center">
  <img src="../assets/readme/anima-edit-ui.jpg" alt="Anima 图像编辑控件" width="920" />
</p>

<p align="center">
  <img src="../assets/readme/anima-edit-sample.jpg" alt="Anima 图像编辑示例" width="760" />
</p>

<p align="center">
  <img src="../assets/readme/anima-edit-sample-1.jpg" alt="Anima 图像编辑示例补充" width="760" />
</p>

<p align="center"><sub>示例图片由 <b>古柯C17H21NO4</b> 提供。感谢他提供用于说明 Anima 图像编辑流程的图片素材。</sub></p>

> WebUI 开启 `conditioning` 后，会自动生成包含 `conditioning_data_dir` 的 `dataset_config`，并在图像编辑预览 prompt 中写入 `--cn <control image>`。
>
> 后端 conditioning 实现参考：[Mirumo0u0/sd-scripts](https://github.com/Mirumo0u0/sd-scripts)。该仓库是 `kohya-ss/sd-scripts` 的 Apache-2.0 fork；本项目保留其许可证文本、修改说明和来源致谢。

## 训练步数经验值

在同一套数据与分辨率下，**约 1000–3000 次优化步** 往往已能呈现可用的角色外观。实际所需步数随素材量、repeat、网络维度、学习率变化很大，请以验证图为准。

**`num batches per epoch`** × **目标 epoch** ≈ 累计步数（例如每 epoch 510 batch → 第 2 个 epoch 结束约 1020 步）。

## 后端架构

本地入口 [`scripts/dev/anima_train_network.py`](../scripts/dev/anima_train_network.py) 是兼容 wrapper：它适配 GUI 生成的 TOML，并委托给 `vendor/sd-scripts` 中的 kohya-ss 后端执行训练。

配置文件：[`config/anima_backend.toml`](../config/anima_backend.toml)

## 进阶：T-LoRA 训练教程

### 什么是 T-LoRA？

T-LoRA（Timestep-Dependent LoRA）是一种改进的 LoRA 方法。普通 LoRA 对所有扩散时间步使用相同的 rank，而 T-LoRA 会**根据当前时间步动态调整有效 rank**——噪声大的时间步使用更高 rank（需要更多表达能力），噪声小的时间步使用更低 rank（避免过拟合细节）。

**优点**：
- 更高效地利用参数，相同 rank 下能学到更多信息
- 正交初始化减少训练早期的不稳定性
- 适合需要精细控制的训练场景

**适合场景**：
- 数据集较小、容易过拟合时
- 希望在不增加模型体积的前提下提升训练效果

### 快速开始

1. 在 Anima LoRA 训练页面，找到「**网络类型**」下拉菜单
2. 选择 **T-LoRA**（排在 LoRA、LoKr 之后）
3. 其他参数照常填写，点击开始训练

选择 T-LoRA 后，系统会自动切换到 T-LoRA 专用的网络模块，并使用优化过的默认参数。

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **网络维度 (network_dim)** | 32 | T-LoRA 的动态 rank 会压缩有效容量，因此通常需要比普通 LoRA 更高的 dim |
| **网络 Alpha (network_alpha)** | 32 | 建议与 network_dim 保持一致，避免学习率被意外缩放 |
| **最小 Rank (tlora_min_rank)** | 4 | 时间步接近 0 时使用的最低 rank。越小越节省参数但容量越低 |
| **Rank 调度 (tlora_rank_schedule)** | linear | rank 随时间步变化的方式。`linear` 为线性插值，`cosine` 更平滑 |
| **正交初始化 (tlora_orthogonal_init)** | 开启 | 用正交矩阵初始化权重，训练更稳定，建议保持开启 |
| **UNet 学习率 (unet_lr)** | — | 由于动态 rank 使得有效梯度更小，可能需要比普通 LoRA 适当提高 |

### 与普通 LoRA 的区别

| | LoRA | T-LoRA |
|---|------|--------|
| Rank | 固定（如 16） | 动态（min_rank ~ network_dim） |
| 收敛速度 | 较快 | 较慢（需要更多步数） |
| 过拟合风险 | 较高 | 较低（低噪声步用低 rank） |
| network_dim | 通常较小即可 | 通常需要更大 |
| 模型体积 | 取决于 dim | 与同 dim 的 LoRA 相同 |

### 常见问题

**Q: T-LoRA 训练很慢，预览图变化不大？**

这是正常的。T-LoRA 的动态 rank 机制会在低噪声时间步降低有效容量，导致收敛比普通 LoRA 慢。可以尝试：
- 增大 `network_dim`
- 增大 `tlora_min_rank`
- 适当提高学习率
- 确保 `tlora_orthogonal_init` 开启
- 耐心多训几个 epoch，T-LoRA 的优势会在后期体现

**Q: T-LoRA 的模型文件可以直接用普通 LoRA 加载吗？**

可以。T-LoRA 的模型权重格式与普通 LoRA 兼容，推理时使用完整 rank（不做时间步动态调整），可以在任何支持 LoRA 的推理工具中正常加载。

**Q: 使用 Automagic / CAME 训练时 loss 变成 NaN？**

优先确认 PyTorch 版本 ≥ 2.5，并避免开启 `full_bf16` / `full_fp16`。Anima 页面仍可使用 `mixed_precision=bf16`，但可训练 LoRA 权重建议保持 FP32；后端会在 `Automagic` 和 `pytorch_optimizer.CAME` 下自动关闭 full 半精度训练，以降低 NaN 风险。不要把 bf16 改成 fp16 作为绕过方案；fp16 数值范围更窄，通常只会让 NaN 晚几步出现。支持 bf16 的显卡上，后端会把这两个优化器的 Anima fp16 配置自动改回 bf16。

**Q: T-LoRA 和 LoKr 哪个好？**

两者解决不同的问题：
- **LoKr** 适合需要高秩、高稀疏度的场景（如 Dense Attention 模型），参数效率更高
- **T-LoRA** 适合需要防止过拟合的场景，通过动态 rank 自适应不同扩散阶段的需求

可以根据实际训练效果选择，也可以都试试对比。

---

## 进阶：LoKr 训练参数参考

对于 Anima 这样的图像模型，由于其 Attention 矩阵是 Dense（高秩）的，传统的 LoRA（低秩）可能在表达能力上存在瓶颈。**LoKr (Kronecker product) 天生适合这种需要高秩、高稀疏度的场景**。

> 以下参数仅供参考，实际效果因数据集、训练目标和硬件环境而异，建议根据自己的情况调整。

1. **起步参数**：
   - `factor` 从较大值（如 `16`）开始尝试
   - LoKr 通常比 LoRA 更耐受较高的学习率，可以在默认值基础上适当提高，观察收敛情况

2. **`full_matrix` 模式**：
   - 开启后 LoKr 使用完整 Kronecker 乘积而非低秩近似，不再需要设置很大的 `dim`
   - 适合希望最大化 LoKr 表达能力的场景

3. **效果不佳时的调整方向**：
   - 逐步降低 `factor`，降低 factor 意味着增加参数量、提升表达能力
   - 降低 `factor` 的同时建议相应降低学习率，避免过拟合
   - `factor` 越小参数量越大，过小时接近全量微调

4. **混合训练**：
   - LoKr 与 LoRA 的性质互补，如果单独使用效果不理想，可以尝试两者结合训练

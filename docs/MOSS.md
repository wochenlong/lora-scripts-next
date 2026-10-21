# MOSS-Image × KohakuMossTrainer 训练教程

> 本教程仅适用于 `KohakuMoss` 独立分支及其专用整合包。`main` / `dev` 的 Kohya、MOSS (anima_lora) 等训练路径不适用本文。

## 1. 先了解这个专用版

此版本只面向 **MOSS-Image Base / SFT**，默认且唯一推荐的训练路径是
**KohakuMossTrainer → LyCORIS**。训练命令保持上游原生形式：

```powershell
kogine run scripts/train/moss.py --config <Next Trainer 生成的 Python 配置>
```

- 专用整合包已内置 `extensions/kohaku-moss/` 完整训练环境，首次启动应直接显示“就绪”。
- 源码版需要在训练页安装一次 KohakuMossTrainer 独立环境。
- 训练页默认选择：**MOSS-Image / KohakuMossTrainer / LoRA**。
- 实际停止条件是 `max_train_steps`；`max_train_epochs` 仅作计划备注。
- 每次训练同时导出 `*-lycoris.safetensors` 与 `*-comfy.safetensors`。

MOSS-Image 不能使用 Anima、Flux 或其他模型家族的权重、缓存与配置。

## 2. 下载训练模型

### Windows 整合包：推荐一键下载

双击：

```text
tools\Download-MOSS-Model.bat
```

下载器从魔搭获取约 27 GB 的 Base BF16 权重，支持断点续传和 SHA256 校验，并自动生成：

```text
Next-Trainer/sd-models/moss-image/
├── dit.safetensors
├── text_encoder.safetensors
├── vae.safetensors
├── tokenizer/
└── download-manifest.json
```

训练页保持默认的 **ComfyUI 拆分单文件** 即可，四个模型路径已经对应这套目录。不要用 ComfyUI 的 INT8/GPTQ 文本编码器代替下载器生成的 BF16 文件。

### 手动准备：原生 Diffusers 目录

源码用户也可以手动下载完整 Hugging Face 目录：

| 组件 | 来源 | 说明 |
|---|---|---|
| Base 全套 | [OpenMOSS-Team/MOSS-Image-Base](https://huggingface.co/OpenMOSS-Team/MOSS-Image-Base) | `transformer` / `text_encoder` / `vae` / `tokenizer`；**支持分片**，无需合并 |
| SFT transformer（可选） | [OpenMOSS-Team/MOSS-Image-SFT](https://huggingface.co/OpenMOSS-Team/MOSS-Image-SFT) | 仅 `model=sft` 时需要；TE/VAE/tokenizer 仍用 Base |

### 手动准备：Comfy 单文件（`comfyui_files`）

| 组件 | 建议来源 | 说明 |
|---|---|---|
| DiT | [Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image) 的 BF16 DiT，或自备单文件 | 支持原生 `q/k/v` 键名，或 Comfy-Org **融合 `qkv`**（首次物化时自动拆成 q/k/v） |
| 文本编码器 | OpenMOSS Base 的 BF16 TE（保留 `language_model.*` 前缀） | Comfy 包里的 int8/GPTQ TE **会被拒绝** |
| VAE | Comfy-Org 的 `flux2-vae.safetensors`，或 OpenMOSS Base VAE | 单文件 `.safetensors` |
| Tokenizer | OpenMOSS Base 的 `tokenizer/`，或 Comfy 包内 `vendor_meta/tokenizer` | 需含 `tokenizer.json`、`tokenizer_config.json`、MOSS chat template |

不支持：分片 `*.safetensors.index.json`（Comfy 模式）、去掉 `language_model.*` 前缀的 TE、int8/GPTQ 等量化权重。

## 3. 怎么存放

把权重放在扩展目录外（例如仓库下的 `sd-models/`）。数据集、缓存、输出也不要放进
`extensions/kohaku-moss/`；该目录只用于专用 Python、训练引擎源码和依赖。

### 原生目录（`native_directory`）

`model_dir` 选**父目录**（同时容纳 Base / 可选 SFT），不要直接选 `transformer/`：

```text
sd-models/moss-image/             ← model_dir
├── MOSS-Image-Base/
│   ├── transformer/             # config.json + 权重或分片+index
│   ├── text_encoder/
│   ├── vae/
│   └── tokenizer/
└── MOSS-Image-SFT/               # 仅 model=sft
    └── transformer/
```

### Comfy 单文件（`comfyui_files`）

示例（路径可按本机调整）：

```text
sd-models/moss-image-comfy/
├── diffusion_models/moss_image_base_bf16.safetensors   → dit_path
├── vae/flux2-vae.safetensors                           → vae_path
└── （TE / tokenizer 可用下方 BF16 包）

sd-models/moss-image-comfy-bf16/
├── text_encoder.safetensors                            → text_encoder_path
└── tokenizer/                                          → tokenizer_path
```

预检/提交时会把 Comfy 文件物化到 `.cache/moss/comfy-layout/<摘要>/`：

- 原生键名：优先硬链 → 符号链接 → 复制  
- Comfy-Org 融合 qkv：首次拆成 `q/k/v` 写入 staging（约再写一份 DiT 体积）；同一摘要会复用

### 数据集

```text
train/moss-image/          ← src
├── 001.png
├── 001.txt                # UTF-8 标注
├── 002.png
└── 002.txt
```

PNG / JPEG / WebP + 同名 `.txt`，可含子目录。最简单的做法是直接把图片与标注放在
`train/moss-image/`；若使用 `1_concept` 这类子目录，目录名前缀会作为重复次数读取。

## 4. 怎么训练

### 4.1 启动前检查

1. 启动 WebUI，确认训练页显示 **MOSS-Image / KohakuMossTrainer / LoRA**。
2. 引擎状态必须为“就绪”。专用整合包若提示安装，说明打包不完整，不要用临时联网安装掩盖问题。
3. 模型使用一键下载器时，保持默认的四个路径：
   - `dit_path = ./sd-models/moss-image/dit.safetensors`
   - `text_encoder_path = ./sd-models/moss-image/text_encoder.safetensors`
   - `vae_path = ./sd-models/moss-image/vae.safetensors`
   - `tokenizer_path = ./sd-models/moss-image/tokenizer`
4. 数据集每张图都应有同名 UTF-8 `.txt` 标注。
5. 输出名称不要包含 `<>:"/\|?*` 等 Windows 非法字符。

### 4.2 第一次先跑 50 steps

第一次不要直接跑长任务，先按以下参数验证模型、数据集、缓存和导出：

| 参数 | 建议值 |
|---|---|
| 底模变体 | `base` |
| 模型加载方式 | `comfyui_files` |
| 训练总步数 | `50` |
| 目标面积 | `1048576`（1024×1024） |
| 标注模式 | 自然语言用 `nl`；逗号 Tag 用 `tags` |
| 网络类型 | `lokr` |
| Rank / Alpha | `32 / 32` |
| 网络范围 | `attn-mlp` |
| 学习率 | `0.0001` |
| 优化器 | `adamw` |
| 显存档位 | 24 GB 用 `balanced`；16 GB 用 `low`；12 GB 左右用 `minimal` |
| 组批方式 | 首次验证用 `count`，Batch size = `1` |
| 混合精度 | `bf16` |
| 底模精度 | `compute` |
| 编译模式 | `off` |
| 算子调优 | Windows 首次验证用 `off` |
| 预览图 | `0`，先关闭 |

点击“校验”后再开始训练。任务应从 step 1 运行到 step 50，loss 必须是有限值，最终在输出目录看到：

```text
<output_name>-lycoris.safetensors
<output_name>-comfy.safetensors
```

### 4.3 正式训练建议

- 20～50 张图可先从 1000～2000 steps 起步；效果是否过拟合应以固定提示词的对比图判断。
- LoKr 默认使用 `factor=8`、`attn-mlp`、Rank/Alpha 32；不熟悉 LyCORIS 时不要同时修改多项结构参数。
- `bucket` 会尽量保留原图比例；数据尺寸混杂时优先使用。
- `latent_cache=online`、`text_cache=online` 会边训练边建立缓存；第二次训练通常更快。
- tokens 组批在图片尺寸不同的情况下吞吐更好；显存不足可把 `max_tokens` 从 12288 降到 8192 或 6144。
- 开启预览会增加显存和耗时。正式训练稳定后再设置 `sample_every_n_steps=200～500`。
- Windows 可以开启 `tune_mode=table`；没有可用 C 编译器时本分支会自动回退。遇到算子编译问题可直接改为 `off`。
- `base_precision=fp8/int8` 属于进阶节省显存方案；首次成功训练前保持 `compute`。

### 4.4 配置示例

```json
{
  "model_train_type": "kohaku-moss-image-lora",
  "model_input_mode": "comfyui_files",
  "model_variant": "base",
  "dit_path": "./sd-models/moss-image/dit.safetensors",
  "text_encoder_path": "./sd-models/moss-image/text_encoder.safetensors",
  "vae_path": "./sd-models/moss-image/vae.safetensors",
  "tokenizer_path": "./sd-models/moss-image/tokenizer",
  "train_data_dir": "./train/moss-image",
  "output_dir": "./output",
  "output_name": "my-moss-lokr",
  "max_train_steps": 50,
  "network_algorithm": "lokr",
  "network_dim": 32,
  "network_alpha": 32,
  "learning_rate": 0.0001,
  "memory_profile": "minimal",
  "batching": "count",
  "batch_size": 1,
  "mixed_precision": "bf16",
  "compile_mode": "off",
  "tune_mode": "off",
  "sample_every_n_steps": 0
}
```

## 5. 训练结果怎么用

1. ComfyUI 优先加载 `*-comfy.safetensors`。
2. 支持 LyCORIS 的加载器可使用 `*-lycoris.safetensors`。
3. 推理必须使用与训练一致的 Base/SFT 变体。
4. 对比训练效果时固定提示词、seed、采样器、steps、CFG 和底模。
5. 不要把 Anima、Flux 或其他引擎的缓存和 LoRA 混入 MOSS 流程。

## 6. 常见问题

### 提示文本编码器不兼容

当前训练器要求 BF16 文本编码器保留 `language_model.*` 权重前缀。不要使用 ComfyUI 的 INT8/GPTQ 文本编码器；重新运行魔搭下载器。

### 首次启动要求安装引擎

源码版属于正常情况；专用整合包则说明训练环境没有正确打入 7z。应联系打包者，不要让最终用户临时重装数 GB 环境。

### Windows 出现 Triton / C 编译器错误

先把“算子自动调优”设为 `off`。本分支已对已知的 `CalledProcessError` 增加 eager 回退；若仍终止，请附完整任务日志反馈。

### 显存不足

按顺序尝试：`balanced → low → minimal`、降低 `max_tokens`、改用 `count + batch_size=1`、关闭预览。不要一开始同时开启 FP8、编译与多卡。

## 7. 上游

- [KohakuMossTrainer](https://github.com/KohakuBlueleaf/KohakuMossTrainer)
- [LyCORIS](https://github.com/KohakuBlueleaf/LyCORIS)
- [MOSS-Image Base](https://huggingface.co/OpenMOSS-Team/MOSS-Image-Base)

Next Trainer 钉住上游提交并应用 Windows Triton 编译失败回退补丁；具体版本以
`mikazuki/engines/kohaku_moss/manifest.py` 为准。

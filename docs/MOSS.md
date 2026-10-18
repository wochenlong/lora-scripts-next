# MOSS-Image LoRA 训练指南（实验性）

## 1. 是什么

Next Trainer 提供两条 **MOSS-Image LoRA** 路径：

- **Kohya（推荐、默认）**：使用内置 `sd-scripts` 的原生 MOSS trainer，功能和维护路径更稳定。
- **MOSS (anima_lora)**：保留为独立运行时的备选方案（流程：预缓存文本/VAE → 训 DiT LoRA）。

MOSS-Image 是独立模型家族，不能套用 Anima / AI Toolkit 的模型、缓存或配置；两种 MOSS 引擎的配置和缓存也不能混用。
- 运行环境在 `extensions/moss/`（钉住上游 [`sorryhyun/anima_lora` @ `moss_lora`](https://github.com/sorryhyun/anima_lora/tree/moss_lora)），与 Anima Fast 分离。
- 上游为 alpha：不保证每张卡的显存上限或成片质量；ComfyUI 侧 LoRA 回载验收可后续补丁。

训练页默认选择：**模型 = MOSS-Image；引擎 = Kohya；目标 = LoRA**。需要原有流程时可手动切换到 **MOSS (anima_lora)**。

## 2. 要提前下载什么模型

安装引擎**不会**下载权重。请按你打算用的输入模式，事先备齐下列组件。

### 方案 A：原生 Diffusers 目录（推荐有官方仓时用）

| 组件 | 来源 | 说明 |
|---|---|---|
| Base 全套 | [OpenMOSS-Team/MOSS-Image-Base](https://huggingface.co/OpenMOSS-Team/MOSS-Image-Base) | `transformer` / `text_encoder` / `vae` / `tokenizer`；**支持分片**，无需合并 |
| SFT transformer（可选） | [OpenMOSS-Team/MOSS-Image-SFT](https://huggingface.co/OpenMOSS-Team/MOSS-Image-SFT) | 仅 `model=sft` 时需要；TE/VAE/tokenizer 仍用 Base |

### 方案 B：Comfy 单文件（`comfyui_files`）

| 组件 | 建议来源 | 说明 |
|---|---|---|
| DiT | [Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image) 的 BF16 DiT，或自备单文件 | 支持原生 `q/k/v` 键名，或 Comfy-Org **融合 `qkv`**（首次物化时自动拆成 q/k/v） |
| 文本编码器 | OpenMOSS Base 的 BF16 TE（保留 `language_model.*` 前缀） | Comfy 包里的 int8/GPTQ TE **会被拒绝** |
| VAE | Comfy-Org 的 `flux2-vae.safetensors`，或 OpenMOSS Base VAE | 单文件 `.safetensors` |
| Tokenizer | OpenMOSS Base 的 `tokenizer/`，或 Comfy 包内 `vendor_meta/tokenizer` | 需含 `tokenizer.json`、`tokenizer_config.json`、MOSS chat template |

不支持：分片 `*.safetensors.index.json`（Comfy 模式）、去掉 `language_model.*` 前缀的 TE、int8/GPTQ 等量化权重。

## 3. 怎么存放

把权重放在扩展目录外（例如仓库下的 `sd-models/`）。数据集、缓存、输出也不要放进 `extensions/moss/`。

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

PNG / JPEG / WebP + 同名 `.txt`，可含子目录；**无需** Kohya「重复次数_概念」目录。

## 4. 怎么训练

### 4.1 Kohya（推荐）

在「设置 → 训练引擎」安装或**修复 Kohya**，然后在训练页选择 MOSS-Image / Kohya / LoRA。此次 MOSS 支持将 Kohya 环境升级为 Transformers 5.17.0、Diffusers 0.40.0、Accelerate 1.15.0；已有 Kohya 环境必须执行一次“修复”才能使用。

模型路径填写规则：

- `pretrained_model_name_or_path`：MOSS DiT 单文件；Diffusers 分片格式请选择第一个 shard（例如 `diffusion_pytorch_model-00001-of-00004.safetensors`）。
- `text_encoder`：Qwen3.5-9B 单文件；分片格式同样选择第一个 shard。
- `vae`：FLUX.2 VAE safetensors。
- `tokenizer_cache_dir`：包含 MOSS chat template 的 tokenizer 目录。
- 数据集使用 Kohya 目录结构，caption 默认并推荐 `.txt`；数据集设置在保存设置之前。

默认启用 latent 与文本编码器输出的磁盘缓存，并只训练 DiT LoRA（`networks.lora_generic`）。预览提示词可直接在预览区文本框填写，提交时转换为 `sample_prompts` 文件。

ConvRot INT8 可分别用于 DiT（`convrot_int8`）和文本编码器（`convrot_int8_text_encoder`）以降低基础权重显存。无 Triton 时可回退但更慢；`convrot_int8_bwd=int8` 则必须有 Triton/CUDA。MOSS 不支持 `fp8_base`。

### 4.2 MOSS (anima_lora) 备选引擎

#### 安装引擎

1. 「设置 → 训练引擎」安装 **MOSS (anima_lora)**，或在训练页选中 MOSS-Image 后点安装。  
2. 走统一任务系统与下载源设置；审计通过后显示「就绪」。  
3. 环境：`extensions/moss/`（`source/`、`.python/`、`.venv/`）。计划依赖 Python 3.13、PyTorch 2.14.1+cu132、Transformers 5.16.1。  
4. 修复会重建该引擎三目录；卸载删除整个 `extensions/moss/`。运行中或排队的 MOSS 任务会阻止安装/修复/卸载。

#### 训练页填写顺序（建议）

1. **模型**：`base` / `sft`；`model_input_mode` = 原生或 Comfy。  
2. **数据集与预缓存**（`src` 已排在分辨率等选项之前）：填数据集目录；`cache_dir` 可留空（自动 `.cache/moss/<摘要>/`）。  
3. **保存**：`output_dir` / `output_name`。  
4. **训练与 LoRA**：短训可用 `epochs=0`、`max_steps=50`、`compile=false`。  
5. **逐轮预览（可选）**：`preview_every_epochs ≥ 1` 时，在 **`preview_prompt` 文本框**直接写提示词（也可用 `preview_prompt_file`；**文本优先**）。预览仍要求 `blocks_to_swap=0`。

#### 提交前检查

- 用界面「校验 / 检查数据」，或 API dry-run（不会真正开训）：

```sh
curl -X POST http://127.0.0.1:28000/api/engines/moss/dry-run \
  -H 'Content-Type: application/json' --data-binary @moss-config.json
```

- 成功时 `training_started=false`；`model_format` 为 `native-diffusers` 或 `comfyui_files`。Comfy-Org DiT 可为 `dit_layout=fused_qkv`。  
- 只有 `/api/run`（或界面「开始训练」）会入队。首次物化融合 qkv 的 DiT 可能多花几分钟。

#### 配置示例

原生：

```json
{
  "model_train_type": "moss-image-anima-lora",
  "model_input_mode": "native_directory",
  "model_dir": "sd-models/moss-image",
  "model": "base",
  "src": "train/moss-image",
  "output_dir": "output/moss",
  "output_name": "my-moss-lora",
  "run_preprocess": true,
  "epochs": 0,
  "max_steps": 50,
  "compile": false
}
```

Comfy（含 Comfy-Org BF16 DiT）：

```json
{
  "model_train_type": "moss-image-anima-lora",
  "model_input_mode": "comfyui_files",
  "model": "base",
  "dit_path": "sd-models/moss-image-comfy/diffusion_models/moss_image_base_bf16.safetensors",
  "text_encoder_path": "sd-models/moss-image-comfy-bf16/text_encoder.safetensors",
  "vae_path": "sd-models/moss-image-comfy/vae/flux2-vae.safetensors",
  "tokenizer_path": "sd-models/moss-image-comfy-bf16/tokenizer",
  "src": "train/moss-image",
  "output_dir": "output/moss",
  "output_name": "my-moss-comfy-lora",
  "run_preprocess": true,
  "epochs": 0,
  "max_steps": 50,
  "compile": false,
  "preview_every_epochs": 0,
  "preview_prompt": ""
}
```

#### 训练中与产出

- 任务页看 progress / loss。  
- 默认倾向：8 epochs、rank 16、`lr=1e-4`、warmup 0.05、LoRA BF16、梯度检查点开、`blocks_to_swap=0`、`compile=false`（Windows 拒绝 compile）。**单卡**；无多卡 / repeats。  
- 缓存：`*.moss_te.safetensors`、`*_宽x高.moss_latent.safetensors`，以及 `.next-moss-cache.json`。改模型/标注/参数时换新 `cache_dir` 或开 `overwrite_cache`。  
- 输出：`<output_name>.safetensors` + 同名 `.json`；周期保存 `<output_name>_eN.safetensors`。

当前不支持：断点续训、加载已有 LoRA 续训、全量微调、量化模型训练、图像编辑训练。

## 5. 怎么使用

1. 训练结束后，在 `output_dir` 取最终或 `_eN` 的 `.safetensors`。  
2. 同名 `.json` 是训练报告（步数、峰值显存、loss 历史等），便于对照参数。  
3. 推理侧：在支持 MOSS-Image 的工作流中加载该 LoRA（例如 ComfyUI 对应节点）。键名与导出格式随上游；若回载异常，先核对是否用了同一套 Base/SFT 变体。  
4. 不要把 Anima / 其他引擎的缓存或 LoRA 混进 MOSS 流程。

## 附录

### 常用参数

`epochs`、`max_steps`、`rank`、`alpha`、`lr`、`warmup_ratio`、`caption_dropout`、`lora_dtype`、`targets`、`sigma_*`、`max_grad_norm`、`grad_checkpointing`、`blocks_to_swap`、`compile`、`log_every`、`seed`、`preview_every_epochs`、`preview_prompt`、`preview_prompt_file`。

### 钉版上游

[`sorryhyun/anima_lora` @ `moss_lora`](https://github.com/sorryhyun/anima_lora/tree/moss_lora)，提交 [`1df6181fcea45926932fb63d5924f6f3dfd7c7d0`](https://github.com/sorryhyun/anima_lora/commit/1df6181fcea45926932fb63d5924f6f3dfd7c7d0)。接口见该提交的 `library/moss/requests.py`。升级产品分支不会自动替换钉版。

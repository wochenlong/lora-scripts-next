# MOSS-Image LoRA 训练指南（实验性）

Next Trainer 通过 **MOSS (anima_lora)** 引擎接入 MOSS-Image Base/SFT 的「预缓存 → LoRA 训练」流程。MOSS-Image 是独立模型，不能套用 Anima / Kohya / AI Toolkit 的模型、缓存或配置。

**过渡说明**：当前训练实现钉住上游 `anima_lora` 的 `moss_lora` 分支，运行环境在 `extensions/moss/`。后续可能迁到 Next 专用引擎；前端 schema、preflight、任务队列与输出契约保持不变。

本机已做过原生目录与 Comfy 单文件（BF16、原生键名）的短训冒烟；ComfyUI 侧 LoRA 回载、浏览器渲染验收仍可后续补丁。上游为 alpha，不保证某张卡的显存上限或成片质量。

## 1. 安装引擎

1. 在「设置 → 训练引擎」安装 **MOSS (anima_lora)**，或在训练页选中 MOSS-Image 后点安装。
2. 安装走统一任务系统与下载源设置（Git / uv / 网络）；审计通过后显示「就绪」。
3. 训练页：**模型 = MOSS-Image；引擎 = MOSS (anima_lora)；目标 = LoRA**。

环境目录：`extensions/moss/`（`source/` 钉版源码、`.python/`、`.venv/`）。计划依赖：Python 3.13、PyTorch 2.14.1+cu132、Transformers 5.16.1。不往 GUI / Kohya / Anima Fast 环境装训练依赖，也不执行上游整仓 `uv sync`。**安装引擎不会下载模型权重。**

修复会重建该引擎的 `source/`、`.python/`、`.venv/`；卸载删除整个 `extensions/moss/`。模型、数据集、缓存、输出请放在扩展目录外。运行中或排队的 MOSS 任务会阻止安装/修复/卸载。

## 2. 选哪种模型格式？

| `model_input_mode` | 适用 | 磁盘要点 |
|---|---|---|
| `native_directory`（默认） | [OpenMOSS Diffusers 仓库](https://huggingface.co/OpenMOSS-Team/MOSS-Image-Base) | **支持分片**，无需合并成单文件 |
| `comfyui_files` | Comfy 风格单文件 + tokenizer 目录 | 每个组件一个 `.safetensors`；物化优先硬链，一般不额外占一整份 |

有官方 Diffusers 目录时优先用原生模式，不必为了 Comfy 模式去合并分片。  
[Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image) 提供 DiT/VAE 单文件；其 TE 常见为 int8/GPTQ，**当前训练入口拒绝量化权重**。Comfy 模式请准备 **BF16 且保留 `language_model.*` 前缀** 的文本编码器（可用 OpenMOSS Base 里的 TE 单文件或自行合并后的 BF16 TE）。

## 3. 原生目录格式（`native_directory`）

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

来源：[MOSS-Image-Base](https://huggingface.co/OpenMOSS-Team/MOSS-Image-Base)、[MOSS-Image-SFT](https://huggingface.co/OpenMOSS-Team/MOSS-Image-SFT)。`model=sft` 仍用 Base 的 TE / VAE / tokenizer。

### 原生模式最小配置示例

```json
{
  "model_train_type": "moss-image-lora",
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

## 4. Comfy 单文件格式（`comfyui_files`）

上游 loader 只认 Diffusers 目录。适配层在预检/提交时把单文件**物化**到 `.cache/moss/comfy-layout/<摘要>/`（硬链 → 符号链接 → 复制），**当前不做键名重写**；键名/尺寸须与原生一致。

| 字段 | 内容 |
|---|---|
| `dit_path` | DiT `.safetensors`（或恰好含一个未分片权重的目录） |
| `text_encoder_path` | Qwen3.5 BF16，键名以 `language_model.*` 开头 |
| `vae_path` | FLUX.2 VAE `.safetensors` |
| `tokenizer_path` | 含 `tokenizer.json`、`tokenizer_config.json`、MOSS chat template |
| `sft_dit_path` | 仅 `model=sft` 时必填 |

不支持：分片 `*.safetensors.index.json`、去掉前缀的纯文本 TE、int8/GPTQ 等量化权重。

推荐布局示例（与 ComfyUI models 习惯接近）：

```text
sd-models/moss-image-comfy/
├── diffusion_models/moss_image_base_bf16.safetensors   → dit_path
├── text_encoders/<bf16-qwen-with-language_model>.safetensors
├── vae/flux2-vae.safetensors
└── tokenizer/   # 可从 OpenMOSS Base 复制
```

### Comfy 模式最小配置示例

```json
{
  "model_train_type": "moss-image-lora",
  "model_input_mode": "comfyui_files",
  "model": "base",
  "dit_path": "sd-models/moss-image-comfy/diffusion_models/moss_image_base_bf16.safetensors",
  "text_encoder_path": "sd-models/moss-image-comfy/text_encoders/text_encoder.safetensors",
  "vae_path": "sd-models/moss-image-comfy/vae/flux2-vae.safetensors",
  "tokenizer_path": "sd-models/moss-image-comfy/tokenizer",
  "src": "train/moss-image",
  "output_dir": "output/moss",
  "output_name": "my-moss-comfy-lora",
  "run_preprocess": true,
  "epochs": 0,
  "max_steps": 50,
  "compile": false
}
```

## 5. 数据集与缓存

- `src`：PNG/JPEG/WebP + 同名 UTF-8 `.txt`，可含子目录；无需 Kohya「重复次数_概念」目录。
- `run_preprocess=true`（默认）：先缓存文本 embedding 与 VAE latent，再训练。
- `cache_dir` 留空：自动分配 `.cache/moss/<摘要>/`。
- `run_preprocess=false`：必须填已有完整缓存的 `cache_dir`，且不要混用其他引擎缓存。
- `resolution`：像素面积上限的平方边长（如 1024 ≈ 1024²），保持比例、不放大小图，编码边长对齐 16。

缓存文件：`*.moss_te.safetensors`、`*_宽x高.moss_latent.safetensors`，外加 `.next-moss-cache.json` 绑定模型与参数。改模型/标注/参数或缓存污染时换新目录。`caption_dropout>0` 可能生成 `_empty.moss_te.safetensors`。

## 6. 推荐训练步骤

1. 安装并等到 MOSS 引擎「就绪」。
2. 准备模型（第三节或第四节）与数据集（第五节）。
3. 训练页选好模式与路径；短训可设 `epochs=0`、`max_steps=50`、`compile=false`。
4. 先 **dry-run / preflight**，确认 `model_format` 为 `native-diffusers` 或 `comfyui_files` 且无错误。
5. 提交训练；任务页看原生 progress/loss。
6. 输出：`<output_name>.safetensors` + 同名 `.json`；周期保存 `<output_name>_eN.safetensors`。

### API dry-run

```sh
curl -X POST http://127.0.0.1:28000/api/engines/moss/dry-run \
  -H 'Content-Type: application/json' --data-binary @moss-config.json
```

成功时 `training_started=false`，并返回解析后的 cache/train 与计划命令。只有 `/api/run` 会真正入队。

## 7. 参数与限制（摘要）

常用原生参数：`epochs`、`max_steps`、`rank`、`alpha`、`lr`、`warmup_ratio`、`caption_dropout`、`lora_dtype`、`targets`、`sigma_*`、`max_grad_norm`、`grad_checkpointing`、`blocks_to_swap`、`compile`、`log_every`、`seed`。

默认倾向：8 epochs、rank 16、`lr=1e-4`、warmup 0.05、LoRA BF16、梯度检查点开、`blocks_to_swap=0`、`compile=false`（Windows 拒绝 compile）。**单卡**；无多卡 / repeats。

当前不支持：断点续训、加载已有 LoRA 续训、全量微调、量化模型训练、图像编辑训练。预览相关能力仍受限。

## 8. 来源

钉版上游：[`sorryhyun/anima_lora` @ `moss_lora`](https://github.com/sorryhyun/anima_lora/tree/moss_lora)，提交 [`1df6181fcea45926932fb63d5924f6f3dfd7c7d0`](https://github.com/sorryhyun/anima_lora/commit/1df6181fcea45926932fb63d5924f6f3dfd7c7d0)。接口见该提交的 `library/moss/requests.py` 与上游 MOSS 说明。升级分支不会自动替换钉版。

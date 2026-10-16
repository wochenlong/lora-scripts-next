# MOSS-Image LoRA（实验性）

Next Trainer 通过 **MOSS (anima_lora)** 引擎接入 MOSS-Image Base/SFT 的原生“预缓存 → LoRA 训练”流程。MOSS-Image 是独立模型，不能套用 Anima 的模型、缓存、LoRA 或训练配置。

**当前验收为 CPU/模拟测试；浏览器渲染检查尚待完成，也未进行真实环境安装、GPU 训练或导出 LoRA 的 ComfyUI 加载验收。** 上游为 alpha；不要据此假定某张显卡的显存需求或训练质量已经得到保证。

## 1. 安装与选择

1. 在“设置 → 训练引擎”中安装 **MOSS (anima_lora)**，或在训练页选中 MOSS-Image 后使用安装按钮。
2. 安装日志及进度使用训练器现有任务系统；环境审计通过后才显示“就绪”。
3. 训练页选择 **模型：MOSS-Image；引擎：MOSS (anima_lora)；目标：LoRA**。

安装器需要可用的 Git、uv 与网络，使用训练器的下载源/网络设置。计划支持 Linux x86_64/aarch64、Windows x86_64 和支持 BF16 的 NVIDIA CUDA GPU；实际平台安装仍待验收。

环境独立保存在 `extensions/moss/`：`source/` 为钉版源码，`.python/` 为托管 Python 3.13，`.venv/` 为依赖环境。当前计划使用 PyTorch 2.14.1 / CUDA 13.2、Transformers 5.16.1；不往 Kohya、Anima Fast 或 GUI Python 中安装训练依赖，也不执行上游整个项目的 `uv sync`。**安装引擎不会下载模型权重。**

修复会重建该引擎的 `source/`、`.python/`、`.venv/`；卸载会移除整个 `extensions/moss/`。请把模型、数据集、缓存、输出保存在该扩展目录之外。正在运行或排队的 MOSS 任务会阻止安装、修复和卸载。

## 2. 原生模型目录

`model_dir` 选择同时容纳各版本的**父目录**，不是直接选择 `transformer/` 或某个权重文件。例如：

```text
sd-models/moss-image/             ← model_dir
├── MOSS-Image-Base/
│   ├── transformer/             # config.json + 原生权重/完整分片及索引
│   ├── text_encoder/            # Qwen3.5-9B 原生目录
│   ├── vae/                     # FLUX.2 VAE 原生目录
│   └── tokenizer/               # tokenizer 配置和 chat template
└── MOSS-Image-SFT/               # 可选，仅 model=sft 时需要
    └── transformer/
```

模型来源：[OpenMOSS-Team/MOSS-Image-Base](https://huggingface.co/OpenMOSS-Team/MOSS-Image-Base)、[OpenMOSS-Team/MOSS-Image-SFT](https://huggingface.co/OpenMOSS-Team/MOSS-Image-SFT)。保留仓库原有配置、权重文件名、索引及分片；`model=sft` 仍使用 **Base** 的文本编码器、VAE 和 tokenizer。

文本编码器必须保留原生 `Qwen3_5Model` / `language_model.*` 结构。此入口不支持 ComfyUI 平铺拆分文件、去掉前缀的纯文本模型或量化权重；也不执行权重转换或键名重写。预检对已覆盖的关键键缺失会报错；检查仅读取本地配置和 safetensors 头部，不等于已经真实加载全部模型。

路径均指训练服务所在机器；相对路径以 Next Trainer 项目根目录解析。

## 3. 数据集与缓存

- `src`：PNG/JPEG/WebP 图片与同名 UTF-8 `.txt`，可包含子目录。无需 Kohya 的重复次数目录；每个图片文件按一个样本处理。
- `run_preprocess=true`（默认）：先运行 MOSS 文本/latent 缓存，再检查缓存，最后训练。
- `cache_dir` 留空：按数据集路径、模型路径和缓存参数分配 `.cache/moss/<摘要>/`。
- `run_preprocess=false`：使用现有缓存，必须明确填写 `cache_dir`；表单不提交 `src`。
- `resolution` 是像素面积上限的平方边长。例如 1024 约为 1024² 像素；保持长宽比、不放大小图，编码尺寸对齐 16。此入口接受 16–4096 的整数面积上限；上游对实际编码宽高对齐 16，不要求这个上限为 16 的倍数。
- `overwrite_cache=false`（默认）：复用有效缓存。`vae_dtype=fp32`、`max_text_tokens=4096` 为默认缓存参数。

不要混用其他引擎缓存。原生缓存包括 `*.moss_te.safetensors`、`*_宽x高.moss_latent.safetensors`；训练器另写 `.next-moss-cache.json` 绑定模型路径、辅助模型文件状态和缓存设置。修改模型/标注/设置、删除样本或出现旧缓存残留时，请优先使用新缓存目录。来源未知的外部缓存即使通过形状检查，也不能证明使用了正确模型和标注。

`caption_dropout>0` 可能额外生成 `_empty.moss_te.safetensors`。已有空提示词缓存来源未知、模型改变或需覆盖时，必须换新缓存目录。`_empty` 为保留样本名。启用 `save_crops` 时，缓存目录不能放在 `src` 内。

## 4. 参数与输出

页面直接使用上游参数：`epochs`、`max_steps`、`rank`、`alpha`、`lr`、`warmup_ratio`、`caption_dropout`、`lora_dtype`、`targets`、`sigma_*`、`max_grad_norm`、`grad_checkpointing`、`blocks_to_swap`、`compile`、`log_every`、`seed` 等。它们不转换为 Kohya `network_*`、优化器参数或 Anima 方法配置。

主要默认值：8 epochs、rank 16、AdamW `lr=0.0001`、warmup 0.05、alpha 留空则使用 rank、LoRA 保存 BF16、梯度检查点开启、`blocks_to_swap=0`、`compile=false`。上游默认启用 compile，本入口为更安全的首次启动显式关闭；Windows 当前拒绝开启 compile。

- **单 GPU、固定 batch size 1**；没有多卡、batch size 或 repeats 参数。
- `max_steps=0` 时由 epochs 决定。两者均大于 0 时，步数为 `min(epochs × 样本数, max_steps)`；`epochs=0` 时必须设置正的 `max_steps`。
- `blocks_to_swap=-1` 自动估计，0 关闭，手动范围 1–40；42 个块至少保留两个在设备侧。自动模式也不保证显存一定足够。
- `save_every_epochs=0` 只保存最终结果。

训练器只做必要的共享表单适配：`cache_dir` → 缓存入口的 `out` / 训练入口的 `cache`，`overwrite_cache` → `overwrite`，`output_dir` + `output_name` → 原生 `output` 路径；GPU 选择用于单卡进程环境。

输出为 `<output_name>.safetensors` 和同名 `.json` 训练报告；周期保存为 `<output_name>_eN.safetensors`。名称不能包含目录分隔符；填写 `.safetensors` 后缀时不会重复添加。已存在的最终文件、报告、周期文件以及排队任务保留的同名空间都会阻止覆盖，请换一个输出名称。

当前不支持断点续训、加载已有 LoRA 继续训练、全量微调、训练中采样预览、图像编辑训练或量化模型训练。任务页读取原生进度/loss 日志，不把其他引擎的预览图当作 MOSS 结果。LoRA 在其他工具中的加载兼容性仍待真实验证。

## 5. 只检查，不启动训练

`POST /api/engines/moss/dry-run` 接收与表单相同的 JSON，返回解析后的 cache/train 参数、计划命令、输入检查结果及 `training_started=false`。它不要求安装完成，不下载模型、不创建训练任务，但要求指定的本地模型和数据/缓存有效。

```sh
curl -X POST http://127.0.0.1:28000/api/engines/moss/dry-run \
  -H 'Content-Type: application/json' --data-binary @moss-config.json
```

最小 `moss-config.json` 示例（路径换成你的真实目录）：

```json
{
  "model_train_type": "moss-image-lora",
  "model_dir": "sd-models/moss-image",
  "model": "base",
  "src": "train/moss-image",
  "output_dir": "output/moss",
  "output_name": "my-moss-lora",
  "run_preprocess": true,
  "compile": false
}
```

`POST /api/engines/moss/install` 加 `{"dry_run":true}` 只返回安装计划。训练提交前的 `/api/engines/moss/preflight` 还会检查已安装环境和 CUDA 可用性；成功也不代表已经验证训练效果。只有正常提交 `/api/run` 才会创建实际训练任务。

## 来源与验收范围

集成钉住 [`sorryhyun/anima_lora` 的 `moss_lora` 分支](https://github.com/sorryhyun/anima_lora/tree/moss_lora)，提交 [`1df6181fcea45926932fb63d5924f6f3dfd7c7d0`](https://github.com/sorryhyun/anima_lora/commit/1df6181fcea45926932fb63d5924f6f3dfd7c7d0)。原生接口见该提交的 [requests.py](https://github.com/sorryhyun/anima_lora/blob/1df6181fcea45926932fb63d5924f6f3dfd7c7d0/library/moss/requests.py) 和 [MOSS 说明](https://github.com/sorryhyun/anima_lora/blob/1df6181fcea45926932fb63d5924f6f3dfd7c7d0/docs/experimental/moss_lora.md)。升级分支并不会自动替换钉版。

已覆盖表单序列化、原生参数解析、头部/缓存校验、导入导出、真实 API 到模拟任务边界、模拟安装状态、取消与恢复。测试没有下载权重、安装训练依赖或执行 GPU 训练。官方模型元数据来源、可复现轻量测试及仍需完成的实机验收见 [FIELD_NOTES](../mikazuki/engines/moss/FIELD_NOTES.md)。

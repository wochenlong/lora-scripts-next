Schema.intersect([
    Schema.object({
        model_train_type: Schema.const("moss-image-anima-lora").default("moss-image-anima-lora").hidden(),
        model: Schema.union(["base", "sft"]).default("base").description("训练版本 / Transformer variant. SFT 仍使用 Base 的文本编码器、VAE 与 tokenizer / SFT reuses Base encoders"),
        model_input_mode: Schema.union(["native_directory", "comfyui_files"]).default("native_directory").description("模型输入方式 / Input mode：native_directory = 官方 Diffusers 目录；comfyui_files = Comfy 风格 DiT/TE/VAE 单文件 + tokenizer 目录。Comfy 文件会物化为原生布局；Comfy-Org 融合 qkv 的 DiT 会在物化时拆成 q/k/v"),
    }).description("MOSS 模型 / Model"),
    Schema.union([
        Schema.object({
            model_input_mode: Schema.const("native_directory"),
            model_dir: Schema.string().role("filepicker", { type: "folder" }).required().default("./sd-models/moss-image").description("模型根目录 / Model root: contains MOSS-Image-Base/{transformer,text_encoder,vae,tokenizer}. SFT additionally requires MOSS-Image-SFT/transformer"),
        }),
        Schema.object({
            model_input_mode: Schema.const("comfyui_files"),
            dit_path: Schema.string().role("filepicker", { type: "model-file", filter: "*.safetensors" }).required().default("./sd-models/moss-image/dit.safetensors").description("Comfy DiT 单文件 / MOSS transformer .safetensors（原生 q/k/v 或 Comfy-Org 融合 qkv；不支持分片索引）"),
            text_encoder_path: Schema.string().role("filepicker", { type: "model-file", filter: "*.safetensors" }).required().default("./sd-models/moss-image/text_encoder.safetensors").description("文本编码器单文件 / Qwen3.5 权重，必须保留 language_model.* 前缀"),
            vae_path: Schema.string().role("filepicker", { type: "model-file", filter: "*.safetensors" }).required().default("./sd-models/moss-image/vae.safetensors").description("VAE 单文件 / FLUX.2 AutoencoderKLFlux2 .safetensors"),
            tokenizer_path: Schema.string().role("filepicker", { type: "folder" }).required().default("./sd-models/moss-image/tokenizer").description("Tokenizer 目录 / 含 tokenizer.json、tokenizer_config.json 与 MOSS chat template"),
            sft_dit_path: Schema.string().role("filepicker", { type: "model-file", filter: "*.safetensors" }).description("SFT DiT 单文件 / Required when model=sft；Base 辅助组件仍用上面的 TE/VAE/tokenizer"),
        }),
    ]),
    Schema.intersect([
      Schema.object({
        run_preprocess: Schema.boolean().default(true).description("先缓存再训练 / Cache text embeddings and VAE latents before training. 关闭时必须已有完整的 MOSS 缓存 / Off requires a complete existing MOSS cache"),
      }),
      Schema.union([
        Schema.object({
            run_preprocess: Schema.const(true),
            src: Schema.string().role("filepicker", { type: "folder", internal: "train-dir" }).required().default("./train/moss-image").description("数据集目录 / Images with matching .txt captions, including subfolders；无需 Kohya 重复次数目录"),
            cache_dir: Schema.string().role("filepicker", { type: "folder" }).description("MOSS 专用缓存 / MOSS cache directory. 留空按数据集自动分配 / Empty: automatic per-dataset cache. 不可使用 Anima 或其他引擎缓存"),
        }),
        Schema.object({
            run_preprocess: Schema.const(false),
            cache_dir: Schema.string().role("filepicker", { type: "folder" }).required().description("已有的完整 MOSS 缓存目录 / Existing complete MOSS cache directory (required when preprocessing is disabled)"),
        }),
      ]),
      Schema.object({
        resolution: Schema.number().role("number", { integer: true }).min(16).max(4096).step(1).default(1024).description("像素面积上限的平方边长 / Pixel-area cap: 1024 means about 1024² pixels. 保持原比例，边长为 16 倍数，不放大小图 / Native aspect, multiples of 16, no upscaling"),
        overwrite_cache: Schema.boolean().default(false).description("强制重建缓存 / Re-encode current caches during preprocessing. 默认复用有效缓存 / Reuse valid caches by default"),
        vae_dtype: Schema.union(["fp32", "bf16"]).default("fp32").description("VAE 缓存精度 / VAE encoding dtype during preprocessing. fp32 为上游默认 / Upstream default is fp32"),
        max_text_tokens: Schema.number().role("number", { integer: true }).min(1).max(4096).step(1).default(4096).description("文本截断长度 / Maximum text tokens during preprocessing, up to the model limit of 4096"),
        save_crops: Schema.boolean().default(false).description("保存缓存输入图 / Also save the exact pixels used to encode each latent during preprocessing"),
      }),
    ]).description("数据集与预缓存 / Dataset and cache"),
    Schema.object({
        output_dir: Schema.string().role("filepicker", { type: "folder" }).required().default("./output/moss").description("输出目录 / LoRA output directory"),
        output_name: Schema.string().required().default("moss-image-lora").description("输出名称 / Output name. 保存为 .safetensors，旁边写入 .json 训练报告 / A JSON run report is saved alongside the LoRA"),
        lora_dtype: Schema.union(["bf16", "fp16", "fp32"]).default("bf16").description("LoRA 保存精度 / Saved LoRA dtype. 训练保留 fp32 主权重，低秩运算为 bf16 / fp32 master weights, bf16 rank operations"),
        save_every_epochs: Schema.number().role("number", { integer: true }).min(0).step(1).default(0).description("每 N 个 epoch 保存 / Save every N epochs; 0 = final only / 仅保存最终结果"),
    }).description("保存设置 / Output"),
    Schema.object({
        batch_size: Schema.number().role("number", { integer: true }).min(1).max(2).step(1).default(1).description("真实批大小 / Simultaneous images per shape bucket. 保留各 bucket 尾批；不使用梯度累积 / Keep partial tails; accumulation=1"),
        epochs: Schema.number().role("number", { integer: true }).min(0).step(1).default(8).description("训练轮数 / Passes over the cached dataset; 0 requires max_steps > 0. 按同尺寸 bucket 组 batch，不使用 repeats / Shape-bucket batches, no repeats"),
        max_steps: Schema.number().role("number", { integer: true }).min(0).step(1).default(0).description("步数上限 / Stop after this many steps; 0 = epochs decide / 由轮数决定"),
        rank: Schema.number().role("number", { integer: true }).min(1).max(3072).step(1).default(16).description("LoRA 秩 / LoRA rank"),
        alpha: Schema.number().min(0.000001).step(1).description("LoRA alpha；留空等于 rank / Empty uses rank"),
        lr: Schema.number().min(1e-12).step(0.00001).default(0.0001).description("AdamW 学习率 / AdamW learning rate"),
        warmup_ratio: Schema.number().min(0).max(1).step(0.01).default(0.05).description("线性预热比例 / Linear warmup as a fraction of all steps"),
        caption_dropout: Schema.number().min(0).max(1).step(0.01).default(0).description("空提示词概率 / Probability of training on the empty-prompt embedding. 大于 0 时自动缓存空文本编码 / Encodes an empty prompt once when positive"),
        seed: Schema.number().role("number", { integer: true }).min(0).step(1).default(0).description("随机种子 / Random seed"),
        log_every: Schema.number().role("number", { integer: true }).min(1).step(1).default(10).description("完整日志间隔 / Full log line every N steps"),
    }).description("训练与 LoRA / Training and LoRA"),
    Schema.object({
        preview_every_epochs: Schema.number().role("number", { integer: true }).min(0).step(1).default(0).description("每 N 轮生成一张预览 / One image every N epochs; 0 disables"),
        preview_prompt: Schema.string().role("textarea").description("预览提示词 / Preview prompt（开启逐轮预览时优先使用；提交时写入缓存 TXT）"),
        preview_prompt_file: Schema.string().role("filepicker", { type: "file" }).description("预览词 TXT 文件 / Caption TXT（未填上方提示词时使用；fingerprint fixed at submission）"),
        preview_width: Schema.number().role("number", { integer: true }).min(16).max(2048).step(16).default(1024).description("预览宽度 / Preview width"),
        preview_height: Schema.number().role("number", { integer: true }).min(16).max(2048).step(16).default(1024).description("预览高度 / Preview height"),
        preview_steps: Schema.number().role("number", { integer: true }).min(1).max(100).step(1).default(30).description("预览采样步数 / Preview denoising steps"),
        preview_seed: Schema.number().role("number", { integer: true }).min(0).step(1).default(42).description("固定预览种子 / Same seed for all epochs"),
    }).description("逐轮预览 / Epoch previews"),
    Schema.object({
        grad_checkpointing: Schema.boolean().default(true).description("梯度检查点 / Per-block activation checkpointing to reduce VRAM use"),
        blocks_to_swap: Schema.number().role("number", { integer: true }).min(-1).max(40).step(1).default(0).description("CPU 交换块数 / DiT blocks swapped to CPU: -1 = auto from free VRAM, 0 = disabled, 1–40 = explicit blocks (at least two blocks remain resident)"),
        compile: Schema.boolean().default(false).description("torch.compile 动态形状编译 / Compile each block with dynamic shapes. 默认关闭以减少首次启动与环境兼容风险 / Disabled by default for safer startup"),
    }).description("显存与编译 / Memory and compilation"),
    Schema.object({
        targets: Schema.string().default("layers\\.\\d+\\.proj\\.(q|k|v|o|ffn_up_gate|ffn_down)").description("LoRA 目标正则 / Fullmatch regex over linear names. 默认覆盖每个块的六个线性层 / Defaults to all six linears per block"),
        sigma_mu: Schema.number().step(0.01).default(-1.09).description("噪声分布均值 / Z ~ N(mu, s²), sigma = 1 - sigmoid(Z)"),
        sigma_s: Schema.number().min(0.000001).step(0.01).default(0.95).description("噪声分布标准差 / Standard deviation of Z"),
        sigma_cutoff: Schema.number().min(0.000001).max(1).step(0.01).default(0.95).description("噪声截断 / Truncate sigma then rescale onto the 1/1000 grid; 1 = off / 关闭截断"),
        sigma_uniform: Schema.number().min(0).max(1).step(0.01).default(0.01).description("均匀噪声混合权重 / Discrete-uniform sigma mixture weight"),
        max_grad_norm: Schema.number().min(0.000001).step(0.1).default(1).description("梯度裁剪 / Maximum gradient norm"),
    }).description("高级训练参数 / Advanced training"),
])

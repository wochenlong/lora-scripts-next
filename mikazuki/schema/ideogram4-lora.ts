Schema.intersect([
    Schema.object({
        model_train_type: Schema.string().default("ideogram4-lora").disabled().description("训练种类"),
        dit: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/ideogram4/ideogram4_fp8_scaled.safetensors").description("Ideogram 4 conditional DiT（FP8 量化底模，官方仅发量化权重；非商用许可，需自行下载）"),
        text_encoder: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/ideogram4/qwen3vl_8b_fp8_scaled.safetensors").description("Qwen3-VL-8B 文本编码器路径（qwen3vl_8b_fp8_scaled）"),
        vae: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/ideogram4/flux2-vae.safetensors").description("VAE 模型路径（Flux2 VAE）"),
        unconditional_dit: Schema.string().role('filepicker', { type: "model-file" }).description("unconditional DiT 路径（可选）。非对称 CFG 推理需要；训练中采样默认只用 conditional DiT，除非在下方开启对应开关"),
        use_unconditional_dit_for_lora_sampling: Schema.boolean().default(false).description("训练中采样使用官方非对称 CFG（需要上面的 unconditional DiT 路径）"),
    }).description("训练用模型"),

    Schema.object({
        timestep_sampling: Schema.union(["ideogram4_shift", "sigma", "uniform", "sigmoid", "shift", "flux_shift"]).default("ideogram4_shift").description("时间步采样。Ideogram 4 官方对齐的取样器为 ideogram4_shift，通常无需修改"),
        ideogram4_timestep_mu: Schema.number().step(0.001).description("ideogram4_shift 采样器的 mu（留空使用官方默认值）"),
        ideogram4_timestep_std: Schema.number().step(0.001).description("ideogram4_shift 采样器的 std（留空使用官方默认值）"),
        min_timestep: Schema.number().min(0).max(1000).step(1).description("最小时间步（0-1000，留空不限制）"),
        max_timestep: Schema.number().min(0).max(1000).step(1).description("最大时间步（0-1000，留空不限制）"),
        validate_caption_structure: Schema.boolean().default(false).description("校验官方结构化 JSON caption（high_level_description / style_description / compositional_deconstruction）。纯文本 caption 默认也接受"),
        warn_on_caption_issues: Schema.boolean().default(false).description("caption 校验失败时仅警告，不中断"),
        log_loss_stats: Schema.boolean().default(false).description("输出 prediction / target 诊断统计（排查发散时使用）"),
    }).description("Ideogram 4 专用参数"),

    Schema.object({
        train_data_dir: Schema.string().role('filepicker', { type: "folder", internal: "train-dir" }).default("./train/aki").description("训练数据集路径（子目录按 Kohya 约定命名为 重复次数_概念名）"),
        resolution: Schema.string().default("1024,1024").description("训练图片分辨率，宽x高。支持非正方形，但必须是 16 倍数。"),
        enable_bucket: Schema.boolean().default(true).description("启用 arb 桶以允许非固定宽高比的图片"),
        bucket_no_upscale: Schema.boolean().default(false).description("arb 桶不放大图片"),
        caption_extension: Schema.string().default(".txt").description("Tag 文件扩展名（官方为结构化 JSON caption；纯文本同样可用）"),
    }).description("数据集设置"),

    Schema.object({
        output_name: Schema.string().default("next-ideogram4-lora").description("模型保存名称（Next Trainer · Ideogram 4 默认；建议按角色/风格自行改名）"),
        output_dir: Schema.string().role('filepicker', { type: "folder" }).default("./output").description("模型保存文件夹"),
        save_precision: Schema.union(["fp16", "float", "bf16"]).default("bf16").description("模型保存精度"),
        save_every_n_epochs: Schema.number().default(2).description("每 N epoch（轮）自动保存一次模型"),
        save_every_n_steps: Schema.number().min(1).description("每 N 步自动保存一次模型（与 save_every_n_epochs 二选一即可）"),
        save_state: Schema.boolean().default(false).description("保存训练状态"),
    }).description("保存设置"),

    Schema.object({
        max_train_epochs: Schema.number().min(1).default(16).description("最大训练 epoch（轮数）"),
        max_train_steps: Schema.number().min(1).description("最大训练步数（设置了 epoch 时由 epoch 推导，可不填）"),
        train_batch_size: Schema.number().min(1).default(1).description("批量大小, 越高显存占用越高"),
        gradient_checkpointing: Schema.boolean().default(true).description("梯度检查点（9.3B 底模建议开启）"),
        gradient_accumulation_steps: Schema.number().min(1).default(1).description("梯度累加步数"),
        seed: Schema.number().default(42).description("随机种子"),
    }).description("训练相关参数"),

    Schema.object({
        learning_rate: Schema.string().default("1e-4").description("学习率"),
        lr_scheduler: Schema.union([
            "linear",
            "cosine",
            "cosine_with_restarts",
            "polynomial",
            "constant",
            "constant_with_warmup",
        ]).default("constant").description("学习率调度器设置"),
        lr_warmup_steps: Schema.number().default(0).description("学习率预热步数"),
        optimizer_type: Schema.union(["AdamW", "AdamW8bit", "Adafactor"]).default("AdamW8bit").description("优化器设置"),
        optimizer_args_custom: Schema.array(String).role('table').description('自定义 optimizer_args，一行一个，例如 weight_decay=0.01'),
        max_grad_norm: Schema.number().step(0.01).default(1.0).description("梯度裁剪阈值，0 为不裁剪"),
    }).description("学习率与优化器设置"),

    Schema.object({
        network_dim: Schema.number().min(1).default(32).description("网络维度（rank）"),
        network_alpha: Schema.number().min(1).default(32).description("常用值：等于 network_dim 或 network_dim*1/2"),
        network_dropout: Schema.number().step(0.01).default(0).description('dropout 概率'),
        network_weights: Schema.string().role('filepicker', { type: "model-file" }).description("从已有的 LoRA 模型上继续训练，填写路径"),
        scale_weight_norms: Schema.number().step(0.01).min(0).description("最大范数正则化。如果使用，推荐为 1"),
        network_args_custom: Schema.array(String).role('table').description("自定义 network_args，一行一个。例如 exclude_patterns=['.*\\.mlp\\..*'] 只训练注意力层"),
    }).description("网络设置"),

    Schema.object({
        mixed_precision: Schema.union(["bf16"]).default("bf16").description("训练混合精度（Ideogram 4 仅支持 bf16）"),
        dit_dtype: Schema.union(["bfloat16", "float16", "float32"]).default("bfloat16").description("DiT 计算精度（底模权重始终以 FP8 加载，这里是计算 dtype）"),
        vae_dtype: Schema.union(["bfloat16", "float16", "float32"]).default("bfloat16").description("VAE 计算精度（缓存 latents 阶段）"),
        text_cache_dtype: Schema.union(["bf16", "fp8_e4m3fn"]).default("bf16").description("文本编码器缓存精度。每 token 需存 53248 通道：bf16 约 13.6 MB/图（1k 图 ≈ 13.6 GB），fp8_e4m3fn 可减半，但会损失精度"),
        blocks_to_swap: Schema.number().min(0).max(33).step(1).default(0).description("交换到内存的 DiT block 数量以节省显存（Ideogram 4 上限 33）"),
        sdpa: Schema.boolean().default(true).description("启用 sdpa"),
        sage_attn: Schema.boolean().default(false).description("启用 SageAttention。Ideogram 4 的 head 维度为 256，不在 SageAttention 支持范围内，会失败"),
        flash_attn: Schema.boolean().default(false).description("启用 Flash Attention（需要额外安装）"),
        split_attn: Schema.boolean().default(false).description("注意力分拆计算，省显存但更慢"),
        persistent_data_loader_workers: Schema.boolean().default(true).description("保留加载训练集的 worker，减少每个 epoch 之间的停顿。"),
        max_data_loader_n_workers: Schema.number().min(0).default(8).description("数据加载器进程数"),
    }).description("显存与精度设置"),

    Schema.object({
        enable_preview: Schema.boolean().default(false).description("启用训练中采样预览图（需要 text_encoder 与 vae 路径）"),
        sample_every_n_epochs: Schema.number().default(2).description("每 N 个 epoch 生成一次预览图"),
        sample_at_first: Schema.boolean().default(false).description("训练开始前先采样一次（用于验证模型与提示词配置）"),
        positive_prompts: Schema.string().role('textarea').default('{"high_level_description": "a photo of a subject", "style_description": "natural lighting", "compositional_deconstruction": "centered subject, plain background"}').description("Prompt。官方推荐结构化 JSON caption（high_level_description / style_description / compositional_deconstruction）"),
        negative_prompts: Schema.string().role('textarea').description("Negative Prompt（官方非对称 CFG 路径忽略该参数）"),
        sampler_preset: Schema.union(["V4_DEFAULT_20", "V4_QUALITY_48", "V4_TURBO_12"]).default("V4_DEFAULT_20").description("采样调度：V4_DEFAULT_20（18+2 步）/ V4_QUALITY_48（45+3 步）/ V4_TURBO_12（11+1 步）"),
        initial_sigma: Schema.number().step(0.001).default(1.004).description("首个去噪 sigma（官方默认 1.004）"),
        sample_width: Schema.number().default(1024).description('预览图宽'),
        sample_height: Schema.number().default(1024).description('预览图高'),
        sample_cfg: Schema.number().min(1).max(30).default(7).description('CFG Scale（官方采样主步 guidance 为 7）'),
        sample_seed: Schema.number().default(42).description('种子'),
        sample_steps: Schema.number().min(1).max(300).default(20).description('迭代步数（与 sampler_preset 对应）'),
        prompt_file: Schema.string().role('textarea').description('预览图 Prompt 文件路径。填写后将采用文件内的 prompt，而下方的选项将失效。'),
    }).description("采样预览设置"),

    Schema.object({
        log_with: Schema.union(["tensorboard", "wandb"]).default("tensorboard").description("日志模块"),
        log_prefix: Schema.string().description("日志前缀"),
        log_tracker_name: Schema.string().description("日志追踪器名称"),
        logging_dir: Schema.string().default("./logs").description("日志保存文件夹"),
        wandb_api_key: Schema.string().description("wandb 的 api 密钥（log_with 选 wandb 时必填）"),
    }).description("日志设置"),

    Schema.object({
        ui_custom_params: Schema.string().role('textarea').description("**危险** 自定义参数，请输入 TOML 格式，将会直接覆盖当前界面内任何参数。实时更新建议写完后再粘贴过来"),
    }).description("其他设置"),
])

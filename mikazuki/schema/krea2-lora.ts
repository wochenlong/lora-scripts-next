Schema.intersect([
    Schema.object({
        model_train_type: Schema.string().default("krea2-lora").disabled().description("训练种类"),
        dit: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/krea2/krea2.safetensors").description("Krea 2 DiT 模型路径（RAW 底模）"),
        vae: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/krea2/qwen_image_vae.safetensors").description("VAE 模型路径（Qwen-Image VAE）"),
        text_encoder: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/krea2/qwen3_vl_4b.safetensors").description("Qwen3-VL-4B 文本编码器路径"),
        turbo_dit: Schema.string().role('filepicker', { type: "model-file" }).description("Turbo 蒸馏 DiT 路径（可选）。填写后训练中采样预览使用 Turbo 调度，训练仍在 RAW 上进行。与 blocks_to_swap 互斥"),
        turbo_dit_cache: Schema.boolean().default(false).description("Turbo 权重常驻内存（M1 模式），加快采样预览切换；需要设置 turbo_dit"),
    }).description("训练用模型"),

    Schema.object({
        timestep_sampling: Schema.union(["sigma", "uniform", "sigmoid", "shift", "flux_shift"]).default("sigmoid").description("时间步采样"),
        sigmoid_scale: Schema.number().step(0.001).default(1.0).description("sigmoid 缩放"),
        discrete_flow_shift: Schema.number().step(0.001).default(1.0).description("Euler 调度器离散流位移"),
        guidance_scale: Schema.number().step(0.01).default(1.0).description("CFG 引导缩放（Krea 2 t2i 训练时通常不使用）"),
        min_timestep: Schema.number().min(0).max(1000).step(1).description("最小时间步（0-1000，留空不限制）"),
        max_timestep: Schema.number().min(0).max(1000).step(1).description("最大时间步（0-1000，留空不限制）"),
    }).description("Krea 2 专用参数"),

    Schema.object({
        train_data_dir: Schema.string().role('filepicker', { type: "folder", internal: "train-dir" }).default("./train/aki").description("训练数据集路径（子目录按 Kohya 约定命名为 重复次数_概念名）"),
        resolution: Schema.string().default("1024,1024").description("训练图片分辨率，宽x高。支持非正方形，但必须是 16 倍数。"),
        enable_bucket: Schema.boolean().default(true).description("启用 arb 桶以允许非固定宽高比的图片"),
        bucket_no_upscale: Schema.boolean().default(false).description("arb 桶不放大图片"),
        caption_extension: Schema.string().default(".txt").description("Tag 文件扩展名"),
    }).description("数据集设置"),

    Schema.object({
        output_name: Schema.string().default("next-krea2-lora").description("模型保存名称（Next Trainer · Krea2 默认；建议按角色/风格自行改名）"),
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
        gradient_checkpointing: Schema.boolean().default(true).description("梯度检查点"),
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
        network_dim: Schema.number().min(1).default(32).description("网络维度（rank），Krea 2 官方推荐 32"),
        network_alpha: Schema.number().min(1).default(32).description("常用值：等于 network_dim 或 network_dim*1/2"),
        network_dropout: Schema.number().step(0.01).default(0).description('dropout 概率'),
        network_weights: Schema.string().role('filepicker', { type: "model-file" }).description("从已有的 LoRA 模型上继续训练，填写路径"),
        scale_weight_norms: Schema.number().step(0.01).min(0).description("最大范数正则化。如果使用，推荐为 1"),
        network_args_custom: Schema.array(String).role('table').description("自定义 network_args，一行一个。例如 exclude_patterns=['.*\\.mlp\\..*'] 只训练注意力层"),
    }).description("网络设置"),

    Schema.object({
        mixed_precision: Schema.union(["bf16"]).default("bf16").description("训练混合精度（Krea 2 仅支持 bf16）"),
        fp8_base: Schema.boolean().default(true).description("DiT 基础权重使用 fp8，大幅降低显存占用。须与 fp8_scaled 同时开启（默认都开）；只开一个会训不起来"),
        fp8_scaled: Schema.boolean().default(true).description("fp8 scaled（动态缩放）。须与 fp8_base 同时开启（默认都开）；只开一个会训不起来"),
        blocks_to_swap: Schema.number().min(0).max(200).step(1).default(0).description("交换到内存的 DiT block 数量以节省显存（与 turbo_dit 互斥）"),
        sdpa: Schema.boolean().default(true).description("启用 sdpa"),
        sage_attn: Schema.boolean().default(false).description("启用 SageAttention（需要额外安装）"),
        flash_attn: Schema.boolean().default(false).description("启用 Flash Attention（需要额外安装）"),
        split_attn: Schema.boolean().default(false).description("注意力分拆计算，省显存但更慢"),
        persistent_data_loader_workers: Schema.boolean().default(true).description("保留加载训练集的 worker，减少每个 epoch 之间的停顿。"),
        max_data_loader_n_workers: Schema.number().min(0).default(8).description("数据加载器进程数"),
    }).description("显存与精度设置"),

    Schema.object({
        enable_preview: Schema.boolean().default(false).description("启用训练中采样预览图"),
        sample_every_n_epochs: Schema.number().default(2).description("每 N 个 epoch 生成一次预览图"),
        sample_at_first: Schema.boolean().default(false).description("训练开始前先采样一次（用于验证模型与提示词配置）"),
        positive_prompts: Schema.string().role('textarea').default('masterpiece, best quality, 1girl, solo').description("Prompt"),
        negative_prompts: Schema.string().role('textarea').description("Negative Prompt（Turbo 采样时通常留空并关闭 CFG）"),
        sample_width: Schema.number().default(1024).description('预览图宽'),
        sample_height: Schema.number().default(1024).description('预览图高'),
        sample_cfg: Schema.number().min(1).max(30).default(4.5).description('CFG Scale（turbo_dit 采样时自动按 1 处理）'),
        sample_seed: Schema.number().default(42).description('种子'),
        sample_steps: Schema.number().min(1).max(300).default(28).description('迭代步数（turbo_dit 采样时自动按 8 处理）'),
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

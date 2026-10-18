Schema.intersect([
    Schema.object({
        model_train_type: Schema.const("moss-image-lora").default("moss-image-lora").hidden(),
        pretrained_model_name_or_path: Schema.string().role("filepicker", { type: "model-file", filter: "*.safetensors" }).required().description("MOSS-Image DiT 权重。Diffusers 分片格式请选择第一个 shard，单文件格式直接选择该文件"),
        text_encoder: Schema.string().role("filepicker", { type: "model-file", filter: "*.safetensors" }).required().description("Qwen3.5-9B 文本编码器。Diffusers 分片格式请选择第一个 shard"),
        vae: Schema.string().role("filepicker", { type: "model-file", filter: "*.safetensors" }).required().description("FLUX.2 VAE 权重"),
        tokenizer_cache_dir: Schema.string().role("filepicker", { type: "folder" }).required().description("MOSS-Image tokenizer 目录，需包含 tokenizer.json 与 tokenizer_config.json"),
    }).description("训练用模型"),

    Schema.object(
        UpdateSchema(SHARED_SCHEMAS.RAW.DATASET_SETTINGS, {
            train_data_dir: Schema.string().role("filepicker", { type: "folder", internal: "train-dir" }).required().default("./train/moss-image").description("训练数据集路径；图片需配同名 .txt 标注"),
            resolution: Schema.string().default("1024,1024").description("训练分辨率，宽x高；MOSS bucket 尺寸需为 16 的倍数"),
            enable_bucket: Schema.boolean().default(true).description("启用宽高比分桶"),
            min_bucket_reso: Schema.number().default(256).description("最小 bucket 分辨率"),
            max_bucket_reso: Schema.number().default(2048).description("最大 bucket 分辨率"),
            bucket_reso_steps: Schema.number().default(16).description("MOSS bucket 分辨率步长，必须为 16"),
        })
    ).description("数据集设置"),

    SHARED_SCHEMAS.SAVE_SETTINGS,

    Schema.object({
        max_train_epochs: Schema.number().min(1).default(8).description("最大训练 epoch"),
        train_batch_size: Schema.number().min(1).default(1).description("训练批量大小"),
        gradient_checkpointing: Schema.boolean().default(true).description("启用梯度检查点"),
        gradient_accumulation_steps: Schema.number().min(1).default(1).description("梯度累加步数"),
        network_train_unet_only: Schema.boolean().default(true).description("仅训练 DiT LoRA；默认不训练 Qwen3.5 文本编码器"),
        network_train_text_encoder_only: Schema.boolean().default(false).description("仅训练文本编码器 LoRA"),
    }).description("训练设置"),

    SHARED_SCHEMAS.LR_OPTIMIZER,

    Schema.object({
        network_module: Schema.const("networks.lora_generic").default("networks.lora_generic").description("MOSS 使用通用 LoRA 网络模块"),
        network_weights: Schema.string().role("filepicker", { type: "model-file" }).description("从已有 LoRA 权重继续训练"),
        network_dim: Schema.number().min(1).default(16).description("LoRA rank"),
        network_alpha: Schema.number().min(1).default(16).description("LoRA alpha"),
        network_dropout: Schema.number().min(0).max(1).step(0.01).default(0).description("LoRA dropout"),
        network_args_custom: Schema.array(String).role("table").description("自定义 network_args，一行一个"),
    }).description("LoRA 网络设置"),

    Schema.object({
        moss_max_token_length: Schema.number().min(1).max(4096).step(1).default(4096).description("MOSS 文本最大 token 数，包含 chat template"),
        timestep_sampling: Schema.union(["sigma", "uniform", "sigmoid", "shift", "flux_shift"]).default("sigmoid").description("时间步采样方式"),
        discrete_flow_shift: Schema.number().step(0.01).default(1).description("Rectified Flow 时间步位移"),
        sigmoid_scale: Schema.number().min(0).step(0.01).default(1).description("Sigmoid 时间步采样缩放"),
        blocks_to_swap: Schema.number().min(0).max(40).step(1).default(0).description("交换到 CPU 的 DiT block 数"),
        convrot_int8: Schema.boolean().default(false).description("加载时将 DiT 基础权重转换为 ConvRot INT8；无 Triton 时使用较慢回退"),
        convrot_int8_text_encoder: Schema.boolean().default(false).description("加载时将 Qwen3.5 文本编码器转换为 ConvRot INT8"),
        convrot_int8_bwd: Schema.union(["bf16", "int8"]).default("bf16").description("ConvRot INT8 反向模式；int8 需要 Triton/CUDA"),
    }).description("MOSS 专用参数"),

    SHARED_SCHEMAS.PREVIEW_IMAGE,
    SHARED_SCHEMAS.LOG_SETTINGS,

    Schema.object(UpdateSchema(SHARED_SCHEMAS.RAW.CAPTION_SETTINGS, {
        caption_extension: Schema.string().default(".txt").description("标注文件扩展名"),
        max_token_length: Schema.number().default(255).hidden(),
    }, ["weighted_captions"])).description("caption（Tag）选项"),

    Schema.object(
        UpdateSchema(SHARED_SCHEMAS.RAW.PRECISION_CACHE_BATCH, {
            mixed_precision: Schema.const("bf16").default("bf16").description("MOSS 训练使用 BF16"),
            sdpa: Schema.boolean().default(true).description("启用 PyTorch SDPA"),
            cache_latents: Schema.boolean().default(true).description("缓存 VAE latent"),
            cache_latents_to_disk: Schema.boolean().default(true).description("将 VAE latent 缓存到磁盘"),
            cache_text_encoder_outputs: Schema.boolean().default(true).description("缓存 Qwen3.5 输出；启用时不能训练文本编码器"),
            cache_text_encoder_outputs_to_disk: Schema.boolean().default(true).description("将文本编码器输出缓存到磁盘"),
            vae_batch_size: Schema.number().min(1).default(1).description("VAE 缓存批量大小"),
        }, ["full_fp16", "full_bf16", "xformers"])
    ).description("精度与缓存"),

    SHARED_SCHEMAS.DATA_ENCHANCEMENT,
    SHARED_SCHEMAS.OTHER,
    SHARED_SCHEMAS.DISTRIBUTED_TRAINING,
])

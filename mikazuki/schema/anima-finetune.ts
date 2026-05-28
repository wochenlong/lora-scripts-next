Schema.intersect([
    Schema.object({
        model_train_type: Schema.string().default("anima-finetune").hidden().description("训练种类"),
        pretrained_model_name_or_path: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/anima/anima-base-v1.0.safetensors").description("Anima 主 DiT / transformer 权重路径（全量微调将更新此 DiT 权重）"),
        vae: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/anima/qwen_image_vae.safetensors").description("Qwen Image VAE 模型路径（Anima 训练必填）"),
        qwen3: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/anima/qwen_3_06b_base.safetensors").description("Qwen3 文本模型路径。可填写 safetensors / pt 文件，或完整本地模型目录"),
        llm_adapter_path: Schema.string().role('filepicker', { type: "model-file" }).description("单独的 LLM Adapter 权重路径（可选）。填写后会覆盖主模型内置 Adapter"),
        t5_tokenizer_path: Schema.string().role('filepicker', { type: "folder" }).description("T5 tokenizer 目录路径（可选，留空使用内置 configs/t5_old）"),
        resume: Schema.string().role('filepicker', { type: "folder" }).description("从某个 `save_state` 保存的中断状态继续训练，填写文件路径"),
    }).description("训练用模型"),

    Schema.object({
        qwen3_max_token_length: Schema.number().step(1).default(512).description("Qwen3 最大 token 长度"),
        t5_max_token_length: Schema.number().step(1).default(512).description("T5 最大 token 长度"),
        timestep_sampling: Schema.union(["sigma", "uniform", "sigmoid", "shift", "flux_shift"]).default("shift").description("时间步采样。默认使用 Anima 推荐的 shift"),
        sigmoid_scale: Schema.number().step(0.001).default(1.0).description("sigmoid 时间步采样缩放"),
        discrete_flow_shift: Schema.number().step(0.001).default(3.0).description("Rectified Flow 位移，默认 3.0"),
        weighting_scheme: Schema.union(["sigma_sqrt", "logit_normal", "mode", "cosmap", "none", "uniform"]).default("uniform").description("时间步分布权重策略"),
        logit_mean: Schema.number().step(0.01).description("logit_normal 权重策略的均值"),
        logit_std: Schema.number().step(0.01).description("logit_normal 权重策略的标准差"),
        mode_scale: Schema.number().step(0.01).description("mode 权重策略的缩放系数"),
        attn_mode: Schema.union(["", "torch", "xformers", "sageattn", "flash"]).default("").description("Attention 加速实现。留空 = 自动选择最优方案"),
        split_attn: Schema.boolean().default(false).description("拆分 attention 计算以降低显存占用"),
        vae_chunk_size: Schema.number().min(2).description("VAE 编码/解码分块大小（需为偶数）"),
        vae_disable_cache: Schema.boolean().default(false).description("禁用内部 VAE 缓存机制"),
        unsloth_offload_checkpointing: Schema.boolean().default(false).description("使用 CPU RAM activation offload 兜底省显存"),
    }).description("Anima 专用参数"),

    Schema.object(
        UpdateSchema(SHARED_SCHEMAS.RAW.DATASET_SETTINGS, {
            resolution: Schema.string().default("1024,1024").description("训练图片分辨率，宽x高。支持非正方形，但必须是 64 倍数。"),
            enable_bucket: Schema.boolean().default(true).description("启用 arb 桶以允许非固定宽高比的图片"),
            min_bucket_reso: Schema.number().default(256).description("arb 桶最小分辨率"),
            max_bucket_reso: Schema.number().default(2048).description("arb 桶最大分辨率"),
            bucket_reso_steps: Schema.number().default(64).description("arb 桶分辨率划分单位"),
        })
    ).description("数据集设置"),

    SHARED_SCHEMAS.SAVE_SETTINGS,

    Schema.object({
        max_train_epochs: Schema.number().min(1).default(10).description("最大训练 epoch（轮数）"),
        train_batch_size: Schema.number().min(1).default(1).description("批量大小，越高显存占用越高"),
        gradient_checkpointing: Schema.boolean().default(true).description("梯度检查点（全量微调强烈建议开启）"),
        gradient_accumulation_steps: Schema.number().min(1).default(1).description("梯度累加步数"),
    }).description("训练相关参数"),

    Schema.intersect([
        Schema.object({
            learning_rate: Schema.string().default("1e-5").description("DiT 全量微调基础学习率（对应上游 anima_train.py --learning_rate）"),
            self_attn_lr: Schema.number().step(1e-7).description("自注意力层学习率（留空=与基础 LR 相同；0=冻结该组件）"),
            cross_attn_lr: Schema.number().step(1e-7).description("交叉注意力层学习率"),
            mlp_lr: Schema.number().step(1e-7).description("MLP 层学习率"),
            mod_lr: Schema.number().step(1e-7).description("AdaLN 调制层学习率"),
            llm_adapter_lr: Schema.number().step(1e-7).description("LLM Adapter 学习率"),
            lr_scheduler: Schema.union([
                "linear",
                "cosine",
                "cosine_with_restarts",
                "polynomial",
                "constant",
                "constant_with_warmup",
            ]).default("cosine_with_restarts").description("学习率调度器设置"),
            lr_warmup_steps: Schema.number().default(0).description("学习率预热步数"),
        }).description("学习率与优化器设置"),
        Schema.union([
            Schema.object({
                lr_scheduler: Schema.const("cosine_with_restarts"),
                lr_scheduler_num_cycles: Schema.number().default(1).description("重启次数"),
            }),
            Schema.object({}),
        ]),
        Schema.object({
            optimizer_type: Schema.union([
                "AdamW",
                "AdamW8bit",
                "Automagic",
                "PagedAdamW8bit",
                "RAdamScheduleFree",
                "Lion",
                "Lion8bit",
                "PagedLion8bit",
                "SGDNesterov",
                "SGDNesterov8bit",
                "DAdaptation",
                "DAdaptAdam",
                "DAdaptAdaGrad",
                "DAdaptAdanIP",
                "DAdaptLion",
                "DAdaptSGD",
                "AdaFactor",
                "Prodigy",
                "prodigyplus.ProdigyPlusScheduleFree",
                "pytorch_optimizer.CAME",
            ]).default("AdamW8bit").description("优化器设置"),
            min_snr_gamma: Schema.number().step(0.1).description("最小信噪比伽马值, 如果启用推荐为 5"),
            optimizer_args_custom: Schema.array(String).role("table").description("自定义 optimizer_args，一行一个"),
        }),
        Schema.union([
            Schema.object({
                optimizer_type: Schema.const("Prodigy").required(),
                prodigy_d0: Schema.string(),
                prodigy_d_coef: Schema.string().default("2.0"),
            }),
            Schema.object({}),
        ]),
    ]),

    Schema.intersect([
        Schema.object({
            enable_preview: Schema.boolean().default(false).description("启用训练预览图"),
        }).description("训练预览图设置"),
        Schema.union([
            Schema.object({
                enable_preview: Schema.const(true).required(),
                positive_prompts: Schema.string().role('textarea').default("1girl, solo, smile, japanese clothes, kimono, blue eyes, closed mouth, upper body, looking at viewer, hair ornament, long hair, yellow kimono, black hair, anime coloring, yukata, choker, split mouth, side ponytail, bow, brown hair").description("预览 Prompt"),
                negative_prompts: Schema.string().role('textarea').default("nsfw, explicit, sexual content, nude, naked, nipples, areola, genitals, cleavage, breasts, ass, buttocks, thighs, underwear, lingerie, bikini, swimsuit, erotic, suggestive, lewd, spread legs, close-up body, transparent clothes, worst quality, low quality, score_1, score_2, score_3, artist name, jpeg artifacts").description("Negative Prompt"),
                sample_width: Schema.number().default(1024).description("预览图宽"),
                sample_height: Schema.number().default(1024).description("预览图高"),
                sample_cfg: Schema.number().min(1).max(30).default(4.5).description("CFG Scale"),
                sample_seed: Schema.number().default(42).description("预览图种子"),
                sample_steps: Schema.number().min(1).max(300).default(40).description("推理步数"),
                sample_sampler: Schema.union(["euler", "k_euler"]).default("euler").description("Anima 训练预览采样器"),
                sample_scheduler: Schema.union(["simple"]).default("simple").description("Anima 预览调度器"),
                sample_at_first: Schema.boolean().default(true).description("训练开始前生成 step 0 预览图"),
                sample_every_n_epochs: Schema.number().default(2).description("每 N 个 epoch 生成一次预览图"),
            }),
            Schema.object({}),
        ]),
    ]),

    SHARED_SCHEMAS.LOG_SETTINGS,

    Schema.intersect([
        Schema.object(UpdateSchema(SHARED_SCHEMAS.RAW.CAPTION_SETTINGS, {
            caption_extension: Schema.string().default(".txt").description("回退读取的 Tag 文件扩展名"),
            shuffle_caption: Schema.boolean().default(false).description("训练时随机打乱 tokens"),
            keep_tokens: Schema.number().min(0).max(255).step(1).default(0).description("随机打乱时保留前 N 个 token 不变"),
            caption_tag_dropout_rate: Schema.number().min(0).step(0.01).description("按标签随机丢弃 tag 的概率"),
            prefer_json_caption: Schema.boolean().default(true).description("优先读取同名 JSON 标签文件"),
        }, ["max_token_length"])).description("caption（Tag）选项"),
        Schema.union([
            Schema.object({
                prefer_json_caption: Schema.const(true).required(),
                json_caption_hint: Schema.string().role('textarea').default("推荐 JSON 结构顺序：quality / count / character / series / artist / appearance[] / tags[] / environment[] / nl。").disabled().description("Anima JSON 标签说明"),
            }),
            Schema.object({}),
        ]),
    ]),

    SHARED_SCHEMAS.NOISE_SETTINGS,
    SHARED_SCHEMAS.DATA_ENCHANCEMENT,
    SHARED_SCHEMAS.OTHER,

    Schema.object(
        UpdateSchema(SHARED_SCHEMAS.RAW.PRECISION_CACHE_BATCH, {
            full_fp16: Schema.boolean().description("完全使用 FP16 精度训练可训练权重"),
            full_bf16: Schema.boolean().description("完全使用 BF16 精度训练可训练权重"),
            fp8_base: Schema.boolean().default(false).description("对基础模型使用 FP8 精度"),
            fp8_base_unet: Schema.boolean().default(false).description("仅对 DiT 使用 FP8 精度"),
            cache_latents: Schema.boolean().default(true).description("缓存 VAE latent，全量微调推荐开启以节省显存"),
            cache_latents_to_disk: Schema.boolean().default(true).description("将 latent 缓存写入磁盘"),
            cache_text_encoder_outputs: Schema.boolean().default(true).description("缓存文本编码器输出（需关闭 shuffle_caption）"),
            cache_text_encoder_outputs_to_disk: Schema.boolean().default(true).description("将文本编码器缓存写入磁盘"),
            persistent_data_loader_workers: Schema.boolean().default(false).description("Windows 下建议关闭"),
            max_data_loader_n_workers: Schema.number().min(0).default(0).description("DataLoader worker 数"),
            text_encoder_batch_size: Schema.number().min(1).description("文本编码器缓存批量大小"),
            disable_mmap_load_safetensors: Schema.boolean().default(false).description("禁用 safetensors 的 mmap 加载"),
            blocks_to_swap: Schema.number().min(1).description("在 CPU/GPU 间交换的 Transformer block 数"),
            cpu_offload_checkpointing: Schema.boolean().default(false).description("梯度检查点时将部分张量卸载到 CPU"),
        }, ["xformers", "sdpa"])
    ).description("速度优化选项"),

    Schema.intersect([
        Schema.object({
            enable_debug_options: Schema.boolean().default(false).description("显示 Anima 调试选项"),
        }).description("调试选项"),
        Schema.union([
            Schema.object({
                enable_debug_options: Schema.const(true).required(),
                anima_profile_window: Schema.number().min(0).default(0).description("每 N 个优化 step 输出一次耗时聚合日志"),
                anima_nan_check_interval: Schema.number().min(0).default(0).description("每 N 个训练 step 检查一次 NaN"),
                anima_debug_mode: Schema.boolean().default(false).description("启用 Anima 详细诊断日志"),
                anima_rope_mismatch_mode: Schema.union(["strict", "resample"]).default("strict").description("RoPE 不匹配处理模式"),
                anima_rope_max_seq_tokens: Schema.number().min(0).default(0).description("Anima 分桶 token 上限预检查"),
            }),
            Schema.object({}),
        ]),
    ]),

    SHARED_SCHEMAS.DISTRIBUTED_TRAINING
]);

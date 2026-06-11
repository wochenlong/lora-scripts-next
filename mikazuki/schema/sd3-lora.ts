Schema.intersect([
    Schema.object({
        model_train_type: Schema.string().default("anima-lora").hidden().description("训练种类"),
        lora_type: Schema.union(["lora", "lokr", "tlora", "lora_fa", "vera", "loha"]).default("lora").description("适配器类型。常规训练建议选择 LoRA"),
        pretrained_model_name_or_path: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/anima/anima-base-v1.0.safetensors").description("Anima 主 DiT / transformer 权重路径，例如 anima-base-v1.0.safetensors"),
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
        attn_mode: Schema.union(["", "torch", "xformers", "sageattn", "flash"]).default("").description("Attention 加速实现。留空 = 自动选择最优方案（优先 Flash Attention 2，其次 xformers，最后 PyTorch SDPA）。推荐留空让系统自动检测。flash 需要安装 flash-attn 且显卡算力≥8.0（RTX 30系+）"),
        split_attn: Schema.boolean().default(false).description("拆分 attention 计算以降低显存占用，通常会牺牲训练速度"),
        vae_chunk_size: Schema.number().min(2).description("VAE 编码/解码分块大小（需为偶数）"),
        vae_disable_cache: Schema.boolean().default(false).description("禁用内部 VAE 缓存机制"),
        unsloth_offload_checkpointing: Schema.boolean().default(false).description("使用 CPU RAM activation offload 兜底省显存；不能与 blocks_to_swap / cpu_offload_checkpointing 同时使用"),
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
        gradient_checkpointing: Schema.boolean().default(true).description("梯度检查点"),
        gradient_accumulation_steps: Schema.number().min(1).default(1).description("梯度累加步数"),
        network_train_unet_only: Schema.boolean().default(true).description("仅训练 DiT / U-Net"),
        network_train_text_encoder_only: Schema.boolean().default(false).description("仅训练 Qwen3 文本编码器"),
    }).description("训练相关参数"),

    SHARED_SCHEMAS.LR_OPTIMIZER,

    Schema.intersect([
        Schema.object({
            network_weights: Schema.string().role('filepicker').description("从已有 LoRA / LoKr 模型继续训练，填写路径"),
            network_dim: Schema.number().min(1).default(16).description("网络维度，常用 4~128，不是越大越好。T-LoRA 建议 32（动态 rank 需要更大基础维度）"),
            network_alpha: Schema.number().min(1).default(16).description("常用值：等于 network_dim 或 network_dim/2 或 1。T-LoRA 建议等于 network_dim"),
            dim_from_weights: Schema.boolean().default(false).description("从已有 network_weights 自动推断 rank / dim"),
            scale_weight_norms: Schema.number().step(0.01).min(0).description("最大范数正则化。如果使用，推荐为 1"),
            train_norm: Schema.boolean().default(false).description("额外训练带可学习权重的 Norm 层"),
            conv_dim: Schema.number().hidden(),
            conv_alpha: Schema.number().hidden(),
            network_args_custom: Schema.array(String).role('table').description("自定义 network_args，一行一个"),
            enable_base_weight: Schema.boolean().default(false).description("启用基础权重（差异炼丹）"),
        }).description("网络设置"),

        Schema.union([
            Schema.object({
                lora_type: Schema.const("lora").default("lora"),
                network_module: Schema.const("networks.lora_anima").default("networks.lora_anima").hidden(),
                network_dropout: Schema.number().step(0.01).default(0).description("LoRA dropout 概率"),
                pissa_init: Schema.boolean().default(false).description("启用 PiSSA 初始化（实验性，仅 LoRA 生效）"),
                lycoris_algo: Schema.string().hidden(),
                lokr_factor: Schema.number().hidden(),
                dropout: Schema.number().hidden(),
            }),
            Schema.object({
                lora_type: Schema.const("lokr").required(),
                network_module: Schema.const("lycoris.kohya").default("lycoris.kohya").hidden(),
                lycoris_algo: Schema.const("lokr").default("lokr").hidden(),
                lokr_factor: Schema.number().min(-1).default(-1).description("LoKr 分解因子。常用 4~无穷，填写 -1 为无穷"),
                full_matrix: Schema.boolean().default(false).description("使用全矩阵模式（高风险）。开启后系统会自动启用保守稳定性护栏：可训练权重保持 FP32，并默认 scale_weight_norms=1"),
                use_cp: Schema.boolean().default(false).description("使用 CP 分解"),
                use_scalar: Schema.boolean().default(false).description("使用可学习缩放系数"),
                decompose_both: Schema.boolean().default(false).description("同时分解输入与输出维度"),
                bypass_mode: Schema.boolean().default(false).description("启用 QLyCORIS bypass 模式"),
                dora_wd: Schema.boolean().default(false).description("启用 DoRA 权重分解"),
                rank_dropout: Schema.number().step(0.01).min(0).max(1).description("rank dropout 概率"),
                module_dropout: Schema.number().step(0.01).min(0).max(1).description("module dropout 概率"),
                rank_dropout_scale: Schema.boolean().default(false).description("对 rank dropout 进行缩放补偿"),
                conv_dim: Schema.number().min(1).description("卷积层维度。不填则跳过卷积层训练"),
                conv_alpha: Schema.number().min(1).description("卷积层 Alpha。通常等于 conv_dim 或 conv_dim/2"),
                dropout: Schema.number().step(0.01).min(0).max(1).description("Dropout 概率"),
                pissa_init: Schema.boolean().hidden(),
                network_dropout: Schema.number().hidden(),
            }),
            Schema.object({
                lora_type: Schema.const("tlora").required(),
                network_module: Schema.const("networks.tlora_anima").default("networks.tlora_anima").hidden(),
                network_dropout: Schema.number().step(0.01).default(0).description("T-LoRA dropout 概率。T-LoRA 自带 rank masking 正则化，一般保持 0 即可"),
                tlora_min_rank: Schema.number().min(1).default(4).description("T-LoRA 最小动态 rank。决定高噪声 timestep 下的最低有效维度，建议 ≥ network_dim/8"),
                tlora_rank_schedule: Schema.union(["cosine", "linear"]).default("cosine").description("T-LoRA 动态 rank 调度。cosine 更平滑（推荐），linear 更激进"),
                tlora_orthogonal_init: Schema.boolean().default(true).description("T-LoRA 对 lora_down 使用正交初始化，加速收敛"),
                pissa_init: Schema.boolean().hidden(),
                lycoris_algo: Schema.string().hidden(),
                lokr_factor: Schema.number().hidden(),
                dropout: Schema.number().hidden(),
            }),
            Schema.object({
                lora_type: Schema.const("lora_fa").required(),
                network_module: Schema.const("networks.lora_anima").default("networks.lora_anima").hidden(),
                network_dropout: Schema.number().step(0.01).default(0).description("LoRA-FA dropout 概率"),
                pissa_init: Schema.boolean().hidden(),
                lycoris_algo: Schema.string().hidden(),
                lokr_factor: Schema.number().hidden(),
                dropout: Schema.number().hidden(),
            }),
            Schema.object({
                lora_type: Schema.const("vera").required(),
                network_module: Schema.const("networks.lora_anima").default("networks.lora_anima").hidden(),
                network_dropout: Schema.number().step(0.01).default(0).description("VeRA dropout 概率"),
                pissa_init: Schema.boolean().hidden(),
                lycoris_algo: Schema.string().hidden(),
                lokr_factor: Schema.number().hidden(),
                dropout: Schema.number().hidden(),
            }),
            Schema.object({
                lora_type: Schema.const("loha").required(),
                network_module: Schema.const("networks.loha").default("networks.loha").hidden(),
                network_dropout: Schema.number().step(0.01).default(0).description("LoHa dropout 概率"),
                pissa_init: Schema.boolean().hidden(),
                lycoris_algo: Schema.string().hidden(),
                lokr_factor: Schema.number().hidden(),
                dropout: Schema.number().hidden(),
            }),
        ]),
        Schema.union([
            Schema.object({
                lora_type: Schema.const("lora").required(),
                pissa_init: Schema.const(true).required(),
                pissa_method: Schema.union(["rsvd", "svd"]).default("rsvd").description("PiSSA 分解方式，推荐保持 rSVD 默认值"),
                pissa_niter: Schema.number().min(0).step(1).default(2).description("PiSSA rSVD 幂迭代次数"),
                pissa_oversample: Schema.number().min(0).step(1).default(8).description("PiSSA rSVD 过采样维度"),
                pissa_apply_conv2d: Schema.boolean().default(false).description("PiSSA 额外作用于 1x1 Conv（实验性）"),
                pissa_export_mode: Schema.union(["LoRA无损兼容导出", "LoRA快速近似导出"]).default("LoRA无损兼容导出").description("PiSSA 模型保存为标准 LoRA 时的导出方式"),
            }),
            Schema.object({}),
        ]),
        SHARED_SCHEMAS.NETWORK_OPTION_BASEWEIGHT,
    ]),

    Schema.intersect([
        Schema.object({
            enable_preview: Schema.boolean().default(false).description("启用训练预览图"),
        }).description("训练预览图设置"),
        Schema.union([
            Schema.object({
                enable_preview: Schema.const(true).required(),
                positive_prompts: Schema.string().role('textarea').default("1girl, solo, smile, japanese clothes, kimono, blue eyes, closed mouth, upper body, looking at viewer, hair ornament, long hair, yellow kimono, black hair, anime coloring, yukata, choker, split mouth, side ponytail, bow, brown hair").description("预览 Prompt。默认使用偏保守的人物半身预览；用户自定义后以后端实际提交值为准"),
                negative_prompts: Schema.string().role('textarea').default("nsfw, explicit, sexual content, nude, naked, nipples, areola, genitals, cleavage, breasts, ass, buttocks, thighs, underwear, lingerie, bikini, swimsuit, erotic, suggestive, lewd, spread legs, close-up body, transparent clothes, worst quality, low quality, score_1, score_2, score_3, artist name, jpeg artifacts").description("Negative Prompt / 负面提示词。默认压制 NSFW、裸露和身体特写，适合公开预览页"),
                sample_width: Schema.number().default(1024).description("预览图宽"),
                sample_height: Schema.number().default(1024).description("预览图高"),
                sample_cfg: Schema.number().min(1).max(30).default(4.5).description("CFG Scale。Anima 官方建议 4-5"),
                sample_seed: Schema.number().default(42).description("预览图种子"),
                sample_steps: Schema.number().min(1).max(300).default(40).description("推理步数。Anima 官方建议 30-50"),
                sample_sampler: Schema.union(["euler", "k_euler"]).default("euler").description("Anima 训练预览采样器（当前为内置 Rectified Flow Euler 预览）"),
                sample_scheduler: Schema.union(["simple"]).default("simple").description("Anima 预览调度器"),
                sample_at_first: Schema.boolean().default(true).description("训练开始前生成 step 0 预览图，用作未训练基线对照。建议开启"),
                sample_every_n_epochs: Schema.number().default(2).description("每 N 个 epoch 生成一次预览图"),
            }),
            Schema.object({}),
        ]),
    ]),

    SHARED_SCHEMAS.LOG_SETTINGS,

    Schema.intersect([
        Schema.object(UpdateSchema(SHARED_SCHEMAS.RAW.CAPTION_SETTINGS, {
            caption_extension: Schema.string().default(".txt").description("回退读取的 Tag 文件扩展名"),
            shuffle_caption: Schema.boolean().default(false).description("训练时随机打乱 tokens；JSON 模式下会对 appearance / tags / environment 分组打乱"),
            keep_tokens: Schema.number().min(0).max(255).step(1).default(0).description("随机打乱时保留前 N 个 token 不变"),
            caption_tag_dropout_rate: Schema.number().min(0).step(0.01).description("按标签随机丢弃 tag 的概率"),
            prefer_json_caption: Schema.boolean().default(true).description("优先读取同名 JSON 标签文件；适合 Anima 结构化标签流程"),
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
            full_fp16: Schema.boolean().description("完全使用 FP16 精度训练可训练权重。Anima 一般不建议开启；Automagic / CAME 会自动禁用以降低 loss=nan 风险。fp16 不是 NaN 绕过方案，支持 bf16 的显卡会自动改回 bf16"),
            full_bf16: Schema.boolean().description("完全使用 BF16 精度训练可训练权重。Anima 一般不建议开启；Automagic / CAME 会自动禁用以降低 loss=nan 风险"),
            fp8_base: Schema.boolean().default(false).description("对基础模型使用 FP8 精度"),
            fp8_base_unet: Schema.boolean().default(false).description("仅对 DiT / U-Net 使用 FP8 精度"),
            cache_text_encoder_outputs: Schema.boolean().default(true).description("缓存文本编码器的输出，减少显存使用。使用时需要关闭 shuffle_caption"),
            cache_text_encoder_outputs_to_disk: Schema.boolean().default(true).description("缓存文本编码器的输出到磁盘"),
            persistent_data_loader_workers: Schema.boolean().default(false).description("Windows 下建议关闭，避免 DataLoader worker 反复导入 xformers 并刷 Triton 提示"),
            max_data_loader_n_workers: Schema.number().min(0).default(0).description("DataLoader worker 数。Anima 默认 0，避免 Windows 多进程启动时重复打印 Triton 警告"),
            text_encoder_batch_size: Schema.number().min(1).description("文本编码器缓存批量大小"),
            disable_mmap_load_safetensors: Schema.boolean().default(false).description("禁用 safetensors 的 mmap 加载"),
            blocks_to_swap: Schema.number().min(1).description("在 CPU/GPU 间交换的 Transformer block 数，用于进一步省显存"),
            cpu_offload_checkpointing: Schema.boolean().default(false).description("实验性显存兜底项：梯度检查点时将部分张量卸载到 CPU"),
        }, ["xformers", "sdpa"])
    ).description("速度优化选项"),

    Schema.intersect([
        Schema.object({
            enable_debug_options: Schema.boolean().default(false).description("显示 Anima 调试选项。普通训练通常不需要开启"),
        }).description("调试选项"),
        Schema.union([
            Schema.object({
                enable_debug_options: Schema.const(true).required(),
                anima_profile_window: Schema.number().min(0).default(0).description("每 N 个优化 step 输出一次耗时聚合日志。0 表示关闭"),
                anima_nan_check_interval: Schema.number().min(0).default(0).description("每 N 个训练 step 检查一次 NaN。0 表示自动决定"),
                anima_debug_mode: Schema.boolean().default(false).description("启用 Anima 详细诊断日志"),
                anima_rope_mismatch_mode: Schema.union(["strict", "resample"]).default("strict").description("RoPE 不匹配处理模式"),
                anima_rope_max_seq_tokens: Schema.number().min(0).default(0).description("Anima 分桶 token 上限预检查。0 表示不限制"),
            }),
            Schema.object({}),
        ]),
    ]),

    SHARED_SCHEMAS.DISTRIBUTED_TRAINING
]);

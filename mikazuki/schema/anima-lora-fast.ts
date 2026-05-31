Schema.intersect([
    Schema.object({
        model_train_type: Schema.string().default("anima-lora-fast").disabled().description("训练种类"),
        lora_type: Schema.const("lora").default("lora").hidden(),
        pretrained_model_name_or_path: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/anima/anima-base-v1.0.safetensors").description("Anima 主 DiT / transformer 权重路径"),
        vae: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/anima/qwen_image_vae.safetensors").description("Qwen Image VAE 模型路径"),
        qwen3: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/anima/qwen_3_06b_base.safetensors").description("Qwen3 文本模型路径"),
        resume: Schema.string().role('filepicker', { type: "folder" }).description("从保存状态继续训练"),
    }).description("训练用模型"),

    Schema.object({
        method: Schema.const("lora").default("lora").hidden(),
        methods_subdir: Schema.const("gui-methods").default("gui-methods").hidden(),
        qwen3_max_token_length: Schema.number().step(1).default(512).description("Qwen3 最大 token 长度"),
        timestep_sampling: Schema.union(["sigma", "uniform", "sigmoid", "shift", "flux_shift"]).default("shift").description("时间步采样"),
        discrete_flow_shift: Schema.number().step(0.001).default(3.0).description("Rectified Flow 位移"),
        attn_mode: Schema.union(["", "torch", "xformers", "sageattn", "flash"]).default("flash").description("Attention 加速实现"),
        torch_compile: Schema.boolean().default(true).description("启用 torch.compile"),
        static_token_count: Schema.number().min(1).default(4096).description("静态 token 上限；bucket 高分辨率训练建议保持 4096 或更高"),
        compile_mode: Schema.union(["blocks", "full"]).default("blocks").description("compile 模式"),
    }).description("Anima Fast 参数"),

    Schema.object({
        train_data_dir: Schema.string().role('filepicker', { type: "folder" }).description("原始训练图片目录（含子文件夹与 .txt caption；与 Kohya 相同结构）"),
        source_image_dir: Schema.string().role('filepicker', { type: "folder" }).description("Anima 原图目录；不填时使用「训练图片目录」"),
        resized_image_dir: Schema.string().role('filepicker', { type: "folder" }).description("训练实际读取的 resized 目录。留空则自动使用 .cache/anima_fast/<数据集路径>/resized 并可复用"),
        lora_cache_dir: Schema.string().role('filepicker', { type: "folder" }).description("Anima LoRA cache 目录；不填时自动使用 .cache/anima_fast"),
        cache_latents: Schema.boolean().default(false).description("使用已预处理的 latent cache；全新训练默认关闭，开启前必须先完成 preprocess"),
        cache_latents_to_disk: Schema.boolean().default(false).description("将 latent cache 写入磁盘"),
        cache_text_encoder_outputs: Schema.boolean().default(false).description("使用已预处理的文本编码 cache；全新训练默认关闭，开启前必须先完成 preprocess"),
        cache_text_encoder_outputs_to_disk: Schema.boolean().default(false).description("将文本编码 cache 写入磁盘"),
        skip_cache_check: Schema.boolean().default(false).description("跳过缓存完整性检查；仅用于已确认缓存完整的高级场景"),
        caption_extension: Schema.string().default(".txt").description("caption 后缀"),
        resolution: Schema.string().default("1024,1024").description("训练图片分辨率"),
        enable_bucket: Schema.boolean().default(true).description("启用 arb 桶"),
    }).description("数据集设置"),

    SHARED_SCHEMAS.SAVE_SETTINGS,

    Schema.object({
        logging_dir: Schema.string().role('filepicker', { type: "folder" }).default("./logs/anima_fast").description("日志目录"),
        progress_jsonl: Schema.string().hidden(),
    }).description("日志与监控"),

    Schema.object({
        max_train_epochs: Schema.number().min(1).default(1).description("最大训练 epoch；设置后 Anima 会按 epoch 和 dataloader 长度重算 step"),
        max_train_steps: Schema.number().min(1).description("最大训练 step；仅在 max_train_epochs 为空时按 step 控制"),
        train_batch_size: Schema.number().min(1).default(1).description("批量大小"),
        gradient_checkpointing: Schema.boolean().default(true).description("梯度检查点"),
        gradient_accumulation_steps: Schema.number().min(1).default(1).description("梯度累加步数"),
        seed: Schema.number().step(1).default(42).description("随机种子"),
    }).description("训练相关参数"),

    SHARED_SCHEMAS.ANIMA_FAST_LR_OPTIMIZER,

    Schema.intersect([
        Schema.object({
            enable_preview: Schema.boolean().default(false).description("启用训练预览图"),
        }).description("训练预览图设置"),
        Schema.union([
            Schema.object({
                enable_preview: Schema.const(true).required(),
                randomly_choice_prompt: Schema.boolean().default(false).description("随机选择预览图 Prompt（训练集仅一个子文件夹且含 .txt 时可用）"),
                prompt_file: Schema.string().role('textarea').description("预览 Prompt 文件路径；填写后优先于下方 positive/negative"),
                positive_prompts: Schema.string().role('textarea').default("1girl, solo, smile, japanese clothes, kimono, blue eyes, closed mouth, upper body, looking at viewer, hair ornament, long hair, yellow kimono, black hair, anime coloring, yukata, choker, split mouth, side ponytail, bow, brown hair").description("预览 Prompt"),
                negative_prompts: Schema.string().role('textarea').default("nsfw, explicit, sexual content, nude, naked, nipples, areola, genitals, cleavage, breasts, ass, buttocks, thighs, underwear, lingerie, bikini, swimsuit, erotic, suggestive, lewd, spread legs, close-up body, transparent clothes, worst quality, low quality, score_1, score_2, score_3, artist name, jpeg artifacts").description("Negative Prompt"),
                sample_width: Schema.number().default(1024).description("预览图宽"),
                sample_height: Schema.number().default(1024).description("预览图高"),
                sample_cfg: Schema.number().min(1).max(30).default(4.5).description("CFG Scale（Anima 建议 4–5）"),
                sample_seed: Schema.number().default(42).description("预览图种子"),
                sample_steps: Schema.number().min(1).max(300).default(40).description("推理步数（Anima 建议 30–50）"),
                sample_sampler: Schema.union(["euler", "k_euler"]).default("euler").description("Anima 训练预览采样器"),
                sample_at_first: Schema.boolean().default(true).description("训练开始前生成 step 0 预览图"),
                sample_every_n_epochs: Schema.number().default(2).description("每 N 个 epoch 生成一次预览图"),
            }),
            Schema.object({}),
        ]),
    ]),

    Schema.object({
        network_module: Schema.const("networks.lora_anima").default("networks.lora_anima").hidden(),
        network_weights: Schema.string().role('filepicker').description("从已有 LoRA 模型继续训练"),
        network_dim: Schema.number().min(1).default(16).description("LoRA 维度"),
        network_alpha: Schema.number().min(1).default(16).description("LoRA alpha"),
        network_dropout: Schema.number().step(0.01).default(0).description("LoRA dropout"),
        network_args_custom: Schema.array(String).role('table').description("自定义 network_args，一行一个 key=value"),
    }).description("网络设置"),
])

Schema.intersect([
    Schema.object({
        model_train_type: Schema.union(["klein-4b-lora", "klein-9b-lora"]).default("klein-4b-lora").description("训练种类（FLUX.2 Klein base 4B / 9B，AI Toolkit 引擎）"),
        dit: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/klein/flux-2-klein-base-4b.safetensors").description("Klein DiT 底模文件（flux-2-klein-base-4b/9b.safetensors，须与训练种类匹配；切换 9B 时改路径），或 HF repo id"),
        text_encoder: Schema.string().role('filepicker', { type: "folder" }).default("./sd-models/klein/qwen3-4b").description("文本编码器目录（Qwen3-4B；训练种类选 9B 时改为 Qwen3-8B 目录）。可在下方「训练用模型」区下载"),
        trigger_word: Schema.string().description("触发词（可选）。填写后会追加到不含该词的 caption 开头"),
    }).description("训练用模型"),

    Schema.object({
        quantize: Schema.boolean().default(true).description("DiT 量化（qfloat8 混合精度），大幅降低显存占用"),
        quantize_te: Schema.boolean().default(true).description("文本编码器（Qwen3）量化"),
        qtype: Schema.union(["qfloat8", "qint8", "qint4"]).default("qfloat8").description("量化类型"),
        low_vram: Schema.boolean().default(false).description("低显存模式（量化时更省显存但更慢）"),
        layer_offloading: Schema.boolean().default(false).description("层级 offload（进一步省显存，显著变慢）"),
    }).description("显存与精度设置（AI Toolkit 专有）"),

    Schema.object({
        train_data_dir: Schema.string().role('filepicker', { type: "folder", internal: "train-dir" }).default("./train/aki").description("训练数据集路径"),
        control_data_dirs: Schema.array(String).role('table').description("图像编辑参考图目录（可选，多个目录按同名文件与训练图配对）"),
        resolution: Schema.string().default("1024,1024").description("训练图片分辨率，宽x高。AI Toolkit 按长边取单分辨率并自动分桶"),
        caption_extension: Schema.string().default(".txt").description("Tag 文件扩展名"),
        caption_dropout_rate: Schema.number().min(0).max(1).step(0.01).description("caption 丢弃概率（0-1）"),
        shuffle_caption: Schema.boolean().default(false).description("随机打乱 caption（按逗号分隔）"),
        dataset_repeats: Schema.number().min(1).description("数据集重复次数（默认 1）"),
    }).description("数据集设置"),

    Schema.object({
        output_name: Schema.string().default("next-klein-lora").description("模型保存名称（建议按角色/风格自行改名）"),
        output_dir: Schema.string().role('filepicker', { type: "folder" }).default("./output").description("模型保存文件夹"),
        save_precision: Schema.union(["bf16", "fp16", "float"]).default("bf16").description("模型保存精度"),
        save_every_n_steps: Schema.number().min(1).default(250).description("每 N 步自动保存一次模型"),
        save_last_n_steps: Schema.number().min(1).default(4).description("保留最近 N 个中间存档"),
    }).description("保存设置"),

    Schema.object({
        max_train_steps: Schema.number().min(1).default(2000).description("最大训练步数（AI Toolkit 无 epoch 概念，一般 500-4000）"),
        train_batch_size: Schema.number().min(1).default(1).description("批量大小, 越高显存占用越高"),
        gradient_checkpointing: Schema.boolean().default(true).description("梯度检查点"),
        gradient_accumulation_steps: Schema.number().min(1).default(1).description("梯度累加步数"),
        max_grad_norm: Schema.number().min(0).step(0.1).default(1.0).description("梯度裁剪阈值（0 或不填走上游默认 1.0）"),
        seed: Schema.number().default(42).description("随机种子"),
    }).description("训练相关参数"),

    Schema.object({
        learning_rate: Schema.string().default("1e-4").description("学习率"),
        lr_scheduler: Schema.union(["constant", "linear", "cosine"]).default("constant").description("学习率调度器设置"),
        optimizer_type: Schema.union(["AdamW", "AdamW8bit", "Adafactor"]).default("AdamW8bit").description("优化器设置"),
        use_ema: Schema.boolean().default(false).description("启用 EMA 平滑（更稳但更慢）"),
        ema_decay: Schema.number().step(0.001).default(0.99).description("EMA 衰减率"),
    }).description("学习率与优化器设置"),

    Schema.object({
        network_dim: Schema.number().min(1).default(16).description("网络维度（rank），对应 AI Toolkit network.linear"),
        network_alpha: Schema.number().min(1).default(16).description("常用值：等于 network_dim 或 network_dim*1/2"),
    }).description("网络设置"),

    Schema.intersect([
        Schema.object({
            enable_preview: Schema.boolean().default(false).description("启用训练中采样预览图"),
        }).description("采样预览设置"),
        Schema.union([
            Schema.object({
                enable_preview: Schema.const(true).required(),
                sample_every_n_steps: Schema.number().min(1).default(250).description("每 N 步生成一次预览图"),
                positive_prompts: Schema.string().role('textarea').default('masterpiece, best quality, 1girl, solo').description("Prompt"),
                negative_prompts: Schema.string().role('textarea').description("Negative Prompt（Klein 通常留空）"),
                sample_width: Schema.number().default(1024).description('预览图宽'),
                sample_height: Schema.number().default(1024).description('预览图高'),
                sample_cfg: Schema.number().min(1).max(30).default(4).description('CFG Scale'),
                sample_seed: Schema.number().default(42).description('种子'),
                sample_steps: Schema.number().min(1).max(300).default(20).description('迭代步数'),
                prompt_file: Schema.string().role('textarea').description('预览图 Prompt 文件路径。填写后将采用文件内的 prompt，而下方的选项将失效。'),
            }),
            Schema.object({}),
        ]),
    ]),

    Schema.object({
        logging_dir: Schema.string().default("./logs").description("日志保存文件夹"),
    }).description("日志设置"),

    Schema.object({
        ui_custom_params: Schema.string().role('textarea').description("**危险** 自定义参数，请输入 TOML 格式，将会直接覆盖当前界面内任何参数。实时更新建议写完后再粘贴过来"),
    }).description("其他设置"),
])

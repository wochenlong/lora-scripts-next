Schema.intersect([
    Schema.object({
        model_source: Schema.union(["local-file", "local-directory", "hf-repo"]).role("model-source-selector").default("local-file").description("模型来源"),
        dit: Schema.string().role('model-path').default("./sd-models/klein/flux-2-klein-base-4b.safetensors").description("支持本地模型文件、本地模型目录或 Hugging Face 仓库 ID"),
        vae_source: Schema.union(["follow-dit", "custom"]).role("vae-source-selector").default("follow-dit").description("VAE 来源"),
        text_encoder: Schema.string().role('filepicker', { type: "folder" }).default("./sd-models/klein/qwen3-4b").description("文本编码器目录；4B 使用 Qwen3-4B，9B 使用 Qwen3-8B"),
        trigger_word: Schema.string().description("触发词（可选）。填写后会追加到不含该词的 caption 开头"),
    }).description("训练用模型").role("section", { group: "model" }),

    Schema.union([
        Schema.object({
            vae_source: Schema.const("custom").required(),
            vae: Schema.string().role('filepicker', { type: "model-file" }).description("单独指定 VAE 模型文件；留空时从 DiT 模型目录寻找 ae.safetensors"),
        }),
        Schema.object({
            vae_source: Schema.const("follow-dit"),
        }),
    ]),

    Schema.object({
        model_train_type: Schema.union(["klein-4b-lora", "klein-9b-lora"]).default("klein-4b-lora").description("训练种类（FLUX.2 Klein base 4B / 9B，AI Toolkit 引擎）"),
    }).description("训练模型类型").role("section", { group: "model_type" }),

    Schema.object({
        quantize: Schema.boolean().default(true).description("DiT 量化（qfloat8 混合精度），大幅降低显存占用"),
        quantize_te: Schema.boolean().default(true).description("文本编码器（Qwen3）量化"),
        qtype: Schema.union(["qfloat8", "qint8", "qint4"]).default("qfloat8").description("DiT / 主模型量化类型"),
        qtype_te: Schema.union(["qfloat8", "qint8", "qint4"]).default("qfloat8").description("文本编码器量化类型"),
        low_vram: Schema.boolean().default(true).description("低显存模式（更省显存但更慢；显存充足时可关闭）"),
        layer_offloading: Schema.boolean().default(false).description("层级 offload（进一步省显存，显著变慢）"),
    }).description("省显存").role("section", { group: "memory" }),

    Schema.intersect([
        Schema.object({
            task: Schema.union(["text-to-image", "image-edit"]).role("task-selector").default("text-to-image").description("训练任务"),
            train_data_dir: Schema.string().role('filepicker', { type: "folder", internal: "train-dir" }).default("./train/data").description("训练数据集路径"),
        }).description("数据集设置").role("section", { group: "dataset" }),
        Schema.union([
            Schema.object({
                task: Schema.const("image-edit").required(),
                control_data_dirs: Schema.array(String).role('paired-directories', { type: "folder", internal: "train-dir" }).description("图像编辑参考图目录（按同名文件与训练图配对）"),
            }),
            Schema.object({
                task: Schema.const("text-to-image"),
            }),
        ]),
        Schema.object({
            resolution: Schema.array(Number).default([512, 768, 1024]).role("resolution-selector").description("训练分辨率档位；可多选或输入自定义数值，AI Toolkit 会自动缩放并分桶"),
            caption_extension: Schema.string().default(".txt").description("Tag 文件扩展名"),
            caption_dropout_rate: Schema.number().min(0).max(1).step(0.01).description("caption 丢弃概率（0-1）"),
            shuffle_caption: Schema.boolean().default(false).description("随机打乱 caption（按逗号分隔）"),
            dataset_repeats: Schema.number().min(1).default(1).description("数据集重复次数"),
        }),
    ]),

    Schema.object({
        output_name: Schema.string().default("next-klein-lora").description("模型保存名称（建议按角色/风格自行改名）"),
        output_dir: Schema.string().role('filepicker', { type: "folder" }).default("./output").description("模型保存文件夹"),
        save_precision: Schema.union(["bf16", "fp16", "float"]).default("bf16").description("模型保存精度"),
        save_every_n_steps: Schema.number().min(1).default(250).description("每 N 步自动保存一次模型"),
        save_last_n_steps: Schema.number().min(1).default(4).description("保留最近 N 个中间存档"),
    }).description("保存设置").role("section", { group: "save" }),

    Schema.object({
        max_train_steps: Schema.number().min(1).default(2000).description("最大训练步数（AI Toolkit 无 epoch 概念，一般 500-4000）"),
        train_batch_size: Schema.number().min(1).default(1).description("批量大小, 越高显存占用越高"),
        gradient_checkpointing: Schema.boolean().default(true).description("梯度检查点"),
        gradient_accumulation_steps: Schema.number().min(1).default(1).description("梯度累加步数"),
        max_grad_norm: Schema.number().min(0).step(0.1).default(1.0).description("梯度裁剪阈值（0 或不填走上游默认 1.0）"),
        seed: Schema.number().default(42).description("随机种子"),
    }).description("训练过程").role("section", { group: "training" }),

    Schema.object({
        learning_rate: Schema.string().default("1e-4").description("学习率"),
        lr_scheduler: Schema.union(["constant", "linear", "cosine"]).default("constant").description("学习率调度器设置"),
        optimizer_type: Schema.union(["AdamW", "AdamW8bit", "Adafactor"]).default("AdamW8bit").description("优化器设置"),
        use_ema: Schema.boolean().default(false).description("启用 EMA 平滑（更稳但更慢）"),
        ema_decay: Schema.number().step(0.001).default(0.99).description("EMA 衰减率"),
    }).description("学习率与优化器").role("section", { group: "optimizer" }),

    Schema.object({
        network_dim: Schema.number().min(1).default(16).description("网络维度（rank），对应 AI Toolkit network.linear"),
        network_alpha: Schema.number().min(1).default(16).description("常用值：等于 network_dim 或 network_dim*1/2"),
    }).description("网络设置").role("section", { group: "network" }),

    Schema.intersect([
        Schema.object({
            enable_preview: Schema.boolean().default(false).description("启用训练中采样预览图"),
        }).description("训练预览图设置").role("section", { group: "preview" }),
        Schema.union([
            Schema.object({
                enable_preview: Schema.const(true).required(),
                sample_every_n_steps: Schema.number().min(1).default(250).description("每 N 步生成一次预览图"),
                positive_prompts: Schema.string().role('preview-sample').default('masterpiece, best quality, 1girl, solo').description("预览样例"),
                preview_samples: Schema.array(String).hidden().description("AI Toolkit 预览 Sample 列表"),
            }),
            Schema.object({}),
        ]),
        Schema.union([
            Schema.object({
                task: Schema.const("image-edit").required(),
                enable_preview: Schema.const(true).required(),
                sample_control_images: Schema.array(String)
                    .role("preview-control-images", { type: "file", internal: "train-dir" }).hidden()
                    .description("图像编辑预览参考图（最多 3 张）"),
            }),
            Schema.object({
                task: Schema.const("text-to-image"),
                enable_preview: Schema.const(true),
            }),
            Schema.object({}),
        ]),
    ]),

    Schema.object({
        logging_dir: Schema.string().default("./logs").description("日志保存文件夹"),
    }).description("日志 / caption / 噪声 / 数据增强").role("section", { group: "logs" }),

    Schema.object({
        ui_custom_params: Schema.string().role('textarea').description("**危险** 自定义参数，请输入 TOML 格式，将会直接覆盖当前界面内任何参数。实时更新建议写完后再粘贴过来"),
    }).description("其他").role("section", { group: "advanced" }),
]).role("training-schema", { capabilities: ["lora", "text-to-image", "image-edit"], task: "text-to-image" })

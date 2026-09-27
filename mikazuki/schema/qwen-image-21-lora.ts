Schema.intersect([
    Schema.object({
        model_train_type: Schema.string().default("qwen-image-21-lora").disabled().description("训练种类"),
        model_input_mode: Schema.union(["directory", "components"]).default("directory").description("模型输入方式：ComfyUI 分组件 / 完整模型目录；首版仅支持 Qwen-Image-2.1 BF16 文生图"),
    }).description("训练用模型"),
    Schema.union([
        Schema.object({
            model_input_mode: Schema.const("directory"),
            diffsynth_model_dir: Schema.string().role('filepicker', { type: "folder" }).required().description("模型目录（transformer / text_encoder / vae）"),
        }),
        Schema.object({
            model_input_mode: Schema.const("components"),
            dit_path: Schema.string().role('filepicker', { type: "model-file", filter: "*.safetensors;*.safetensors.index.json" }).required().description("Comfy-Org Qwen-Image-2.1 BF16 DiT；可填写文件、分片索引或目录"),
            text_encoder_path: Schema.string().role('filepicker', { type: "model-file", filter: "*.safetensors;*.safetensors.index.json" }).required().description("Qwen3-VL-8B BF16 文本编码器"),
            vae_path: Schema.string().role('filepicker', { type: "model-file", filter: "*.safetensors;*.safetensors.index.json" }).required().description("Qwen-Image-2.1 BF16 VAE"),
        }),
    ]),
    Schema.object({
        dataset_format: Schema.union(["image_text", "metadata"]).default("image_text").description("数据集格式：图片 + TXT / 原生 CSV、JSON、JSONL"),
    }).description("数据集设置"),
    Schema.union([
        Schema.object({
            dataset_format: Schema.const("image_text"),
            train_data_dir: Schema.string().role('filepicker', { type: "folder", internal: "train-dir" }).default("./train/qwen-image-21").required().description("图片与同名 TXT；支持 重复次数_概念名 子目录，普通目录和根目录图片均保留"),
            dataset_repeat: Schema.number().min(1).step(1).default(1).description("全局重复次数，与子目录重复次数相乘"),
        }),
        Schema.object({
            dataset_format: Schema.const("metadata"),
            dataset_base_path: Schema.string().role('filepicker', { type: "folder" }).required().description("元数据中图片相对路径的根目录"),
            dataset_metadata_path: Schema.string().role('filepicker', { type: "file", filter: "*.csv;*.json;*.jsonl" }).required().description("包含 image、prompt 字段的原生元数据；不按文件夹名重复"),
        }),
    ]),
    Schema.object({
        resolution: Schema.string().default("1024,1024").description("训练图片基准分辨率，宽,高；支持非正方形，宽高必须是 64 倍数。宽×高决定像素面积"),
        enable_bucket: Schema.boolean().default(true).description("开启：使用 Kohya 分辨率桶。关闭：回退原 DiffSynth 策略，超过 resolution 宽×高面积时等比缩小，宽高向下对齐 32 后中心裁剪；小图不放大，不强制裁成填写的宽高。关闭后仅相同实际尺寸可组批，可能出现更多小 batch"),
        min_bucket_reso: Schema.number().min(32).step(32).default(256).description("最小桶边长；必须是桶步长的倍数"),
        max_bucket_reso: Schema.number().min(64).step(32).default(2048).description("最大桶边长；不小于基准分辨率宽高"),
        bucket_reso_steps: Schema.number().min(32).step(32).default(64).description("桶分辨率步长；越大桶越少、越容易组满 batch，但裁剪可能更多"),
        bucket_no_upscale: Schema.boolean().default(false).description("桶不放大图片；开启后按原图生成桶，最小/最大桶边长不生效，小图可能形成更多小桶"),
    }),
    Schema.object({
        output_dir: Schema.string().role('filepicker', { type: "folder" }).default("./output").required().description("模型保存目录"),
        output_name: Schema.string().default("qwen-image-21-lora").required().description("任务名称，每次训练保存到独立子目录"),
        save_steps: Schema.number().min(1).step(1).description("每 N 次优化器更新保存权重；留空则每轮保存。权重不含优化器状态"),
    }).description("保存设置"),
    Schema.object({
        num_epochs: Schema.number().min(1).step(1).default(5).description("训练轮数"),
        learning_rate: Schema.string().default("1e-4").description("基础学习率；预热结束时达到此值"),
        lr_scheduler: Schema.union(["constant", "linear", "cosine", "cosine_with_restarts"]).default("constant").description("学习率调度：恒定 / 线性衰减 / 余弦衰减 / 余弦重启"),
        lr_warmup_steps: Schema.number().min(0).step(1).default(0).description("学习率预热步数；按优化器更新计数，0 为不预热"),
        optimizer_type: Schema.union(["AdamW", "AdamW8bit"]).default("AdamW").description("优化器；AdamW8bit 使用 8 位优化器状态，降低显存占用"),
        train_batch_size: Schema.number().min(1).step(1).default(1).description("真实 batch size；相同分辨率桶内组批，尾批保留。大于 1 时需开启预编码缓存"),
        gradient_accumulation_steps: Schema.number().min(1).step(1).default(1).description("梯度累积步数；每 N 个 batch 更新一次参数"),
        lora_rank: Schema.number().min(1).step(1).default(32).description("LoRA Rank"),
        lora_alpha: Schema.number().min(0.001).description("LoRA Alpha；留空等于 Rank，缩放系数为 Alpha / Rank"),
        lora_target_modules: Schema.string().default("").description("LoRA 目标层，以逗号分隔；留空由官方脚本自动选择目标层"),
        lora_checkpoint: Schema.string().role('filepicker', { type: "model-file" }).description("可选：从已有 LoRA 权重继续训练（不恢复优化器）"),
    }).description("训练参数"),
    Schema.union([
        Schema.object({
            lr_scheduler: Schema.const("cosine_with_restarts"),
            lr_restart_count: Schema.number().min(0).step(1).default(1).description("余弦重启次数；1 次重启对应 2 个余弦周期，不重复预热"),
        }),
        Schema.object({ lr_scheduler: Schema.const("constant") }),
        Schema.object({ lr_scheduler: Schema.const("linear") }),
        Schema.object({ lr_scheduler: Schema.const("cosine") }),
    ]),
    Schema.object({
        cache_embeddings: Schema.boolean().default(false).description("预编码缓存：先缓存 TE 文本特征与 VAE 图片 latent，再卸载编码器，仅训练 DiT；预览使用缓存文本并临时加载 VAE"),
        use_gradient_checkpointing: Schema.boolean().default(true).description("梯度检查点，节省显存"),
        use_gradient_checkpointing_offload: Schema.boolean().default(false).description("将梯度检查点卸载到内存"),
        initialize_model_on_cpu: Schema.boolean().default(true).description("在 CPU 初始化模型，降低启动显存峰值"),
        enable_model_cpu_offload: Schema.boolean().default(false).description("逐层将模型权重从 CPU 加载到 GPU，节省显存但会变慢"),
    }).description("显存设置（单卡 BF16）"),
    Schema.object({
        sample_enabled: Schema.boolean().default(false).description("训练中预览；与模型 CPU 卸载同时使用时必须开启预编码缓存"),
    }).description("预览设置"),
    Schema.union([
        Schema.object({
            sample_enabled: Schema.const(true),
            sample_every_n_steps: Schema.number().min(1).step(1).default(100).description("每 N 次优化器更新预览，与保存步数使用同一口径；失败时任务报错停止"),
            sample_every_n_epochs: Schema.number().min(1).step(1).description("每 N 个 epoch 完成后预览；留空使用步数出图，填写后覆盖步数出图设置"),
            preview_samples: Schema.array(String).role('preview-samples', { dimensionStep: 32, minGuidance: 1 }).default(['{"prompt":"","width":1024,"height":1024,"seed":42,"guidance_scale":4,"sample_steps":20}']).description("预览样例，可添加多组独立参数"),
        }),
        Schema.object({ sample_enabled: Schema.const(false) }),
    ]),
])

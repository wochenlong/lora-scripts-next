Schema.intersect([
    Schema.object({
        model_train_type: Schema.const("kohaku-moss-image-lora").default("kohaku-moss-image-lora").hidden(),
        pretrained_model_name_or_path: Schema.string().role("filepicker", { type: "folder" }).required()
            .description("MOSS-Image Base/SFT 的 Hugging Face 权重目录（transformer、text_encoder、vae）。实验性高性能引擎"),
        train_data_dir: Schema.string().role("filepicker", { type: "folder", internal: "train-dir" }).required()
            .default("./train/moss-image").description("kohya 风格数据集目录；图片配同名 .txt 标注"),
    }).description("实验性 KohakuMossTrainer · 感谢 Kohaku / 龙娘与 LyCORIS 社区"),

    Schema.object({
        output_dir: Schema.string().role("filepicker", { type: "folder" }).required().default("./output")
            .description("KohakuMossTrainer 运行目录根路径"),
        output_name: Schema.string().required().default("kohaku-moss-lora").description("运行名与导出文件名前缀"),
        max_train_steps: Schema.number().min(1).default(1000).description("原生训练步数（v1 的实际停止条件）"),
        max_train_epochs: Schema.number().min(0).default(0)
            .description("Epoch 计划备注；上游原生按 steps 驱动，v1 仍以 max_train_steps 为准"),
        save_every_n_steps: Schema.number().min(0).default(500).description("每 N 步保存；0 为关闭"),
        sample_every_n_steps: Schema.number().min(0).default(0).description("每 N 步采样；0 为关闭"),
        seed: Schema.number().min(0).default(0),
    }).description("训练与输出"),

    Schema.object({
        network_algorithm: Schema.union(["lora", "locon", "loha", "lokr", "oft", "boft", "glora", "ia3", "dylora", "tlora"])
            .default("lora").description("LyCORIS 算法"),
        network_dim: Schema.number().min(1).default(32).description("适配器 rank / dimension"),
        network_alpha: Schema.number().min(0).default(32).description("适配器 alpha"),
        learning_rate: Schema.number().min(0).step(0.000001).default(0.0001),
    }).description("LyCORIS 网络"),

    Schema.object({
        memory_profile: Schema.union(["speed", "balanced", "low", "minimal", "auto"]).default("balanced")
            .description("上游显存方案；minimal 可面向 6–8 GB 显卡，仍需足够系统内存"),
        mixed_precision: Schema.union(["bf16", "fp16", "auto"]).default("bf16")
            .description("计算精度；不支持 BF16 的旧卡请选择 fp16 或 auto"),
    }).description("高性能与显存"),
])

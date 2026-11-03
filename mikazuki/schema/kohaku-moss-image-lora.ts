Schema.intersect([
    Schema.intersect([
        Schema.object({
            model_train_type: Schema.const("kohaku-moss-image-lora").default("kohaku-moss-image-lora").hidden(),
            model_variant: Schema.union(["base", "sft"]).default("base")
                .description("底模变体（base 或 sft，需与所选权重一致）"),
            model_input_mode: Schema.union(["comfyui_files", "native_directory"]).default("comfyui_files")
                .description("模型加载方式（comfyui_files = ComfyUI 拆分单文件；native_directory = 完整 Hugging Face 目录）"),
        }).description("核心必填与基础训练设置"),

        Schema.union([
            Schema.object({
                model_input_mode: Schema.const("comfyui_files").required(),
                dit_path: Schema.string().role("filepicker", { type: "model-file", filter: "*.safetensors" }).required()
                    .default("./sd-models/moss-image/dit.safetensors")
                    .description("【必填】DiT 主模型单文件（.safetensors；支持原生 q/k/v 或 Comfy-Org 融合 qkv 权重，选 SFT 变体时请直接选 SFT 的 DiT 文件）"),
                text_encoder_path: Schema.string().role("filepicker", { type: "model-file", filter: "*.safetensors" }).required()
                    .default("./sd-models/moss-image/text_encoder.safetensors")
                    .description("【必填】Qwen3.5 文本编码器单文件（.safetensors；需保留 language_model.* 前缀）"),
                vae_path: Schema.string().role("filepicker", { type: "model-file", filter: "*.safetensors" }).required()
                    .default("./sd-models/moss-image/vae.safetensors")
                    .description("【必填】FLUX.2 VAE 单文件（.safetensors）"),
                tokenizer_path: Schema.string().role("filepicker", { type: "folder" }).required()
                    .default("./sd-models/moss-image/tokenizer")
                    .description("【必填】Tokenizer 分词器目录（含 tokenizer.json、tokenizer_config.json 与对话模板）"),
            }),
            Schema.object({
                model_input_mode: Schema.const("native_directory").required(),
                pretrained_model_name_or_path: Schema.string().role("filepicker", { type: "folder" }).required()
                    .default("./sd-models/moss-image")
                    .description("【必填】MOSS-Image 完整目录（可直接选含 transformer/text_encoder/vae 的目录，或含 MOSS-Image-Base 的上级目录）"),
            }),
        ]),

        Schema.object({
            train_data_dir: Schema.string().role("filepicker", { type: "folder", internal: "train-dir" }).required()
                .default("./train/moss-image").description("【必填】数据集目录（子文件夹如 1_concept，内含图片与同名 .txt 标注）"),
            output_dir: Schema.string().role("filepicker", { type: "folder" }).required().default("./output")
                .description("【必填】模型与日志输出根目录"),
            output_name: Schema.string().required().default("kohaku-moss-lora")
                .description("【必填】模型名称（导出的 LoRA 文件名前缀）"),
            max_train_steps: Schema.number().min(1).default(1000)
                .description("训练总步数（STEPS；常规 20~50 张图建议 1000~2000 步）"),
            save_every_n_steps: Schema.number().min(0).default(500)
                .description("每 N 步保存一次权重；0 为仅结束时保存"),
            optimizer_type: Schema.union([
                "adamw", "adamw16", "adamw8bit", "adamw8bit_kernel", "muon", "prodigy", "schedule_free",
            ]).default("adamw").description("优化器类型（low / minimal 仅支持 adamw；其他档位也可选 8bit 等优化器）"),
            learning_rate: Schema.number().min(0).step(0.000001).default(0.0001)
                .description("学习率（默认 0.0001 即 1e-4）"),
        }),
    ]),

    Schema.object({
        sample_every_n_steps: Schema.number().min(0).default(0)
            .description("每 N 步生成一张预览图；0 为关闭（开启建议设为 200~500）"),
        sample_prompts: Schema.string().role("textarea")
            .default("masterpiece, best quality, 1girl, solo, smile, upper body, looking at viewer, soft lighting, clean background")
            .description("预览正面提示词；每行一条，开启预览后至少保留一条"),
        sample_negative: Schema.string().role("textarea")
            .default("lowres, blurry, worst quality, low quality, bad anatomy, bad hands, extra digits, watermark, text")
            .description("预览负面提示词（可选）"),
        sample_width: Schema.number().min(256).max(2048).step(64).default(1024).description("预览图宽"),
        sample_height: Schema.number().min(256).max(2048).step(64).default(1024).description("预览图高"),
        sample_steps: Schema.number().min(1).max(100).default(50).description("预览推理步数（默认 50）"),
        sample_cfg: Schema.number().min(0).max(30).step(0.1).default(3.0).description("预览 CFG 引导强度（默认推荐 3.0）"),
        sample_shift: Schema.number().min(0).max(20).step(0.1).default(5.0).description("预览时间步偏移 shift（默认推荐 5.0）"),
        sample_seed: Schema.number().min(0).default(0).description("预览随机种子"),
    }).description("训练预览图（按需开启）"),

    Schema.intersect([
        Schema.object({
            memory_profile: Schema.union(["speed", "balanced", "low", "minimal", "auto"]).default("balanced")
                .description("显存优化档位（balanced 适合 24GB；low 适合 16GB；minimal 适合 12GB；speed 适合大显存提速）"),
            caption_mode: Schema.union(["nl", "tags"]).default("nl")
                .description("标注文本解析方式（nl = 自然语言或固定顺序文本，原样读取不按逗号打乱；tags = 逗号分隔 Tag 标签，训练时随机打乱顺序）"),
            resolution_mode: Schema.union(["bucket", "resize", "shifted_square", "square_crop"]).default("bucket")
                .description("图片长宽比处理方式（bucket 自动分桶保持原图比例；resize 缩放裁切为正方）"),
            target_area: Schema.number().min(65536).default(1048576)
                .description("目标像素总面积（默认 1048576 即 1024×1024；768×768 可填 589824）"),
            network_algorithm: Schema.union([
                "lokr", "lora", "locon", "loha", "oft", "boft", "glora", "ia3", "dylora", "tlora",
            ]).default("lokr").description("微调网络类型（默认推荐 lokr）"),
        }).description("常用核心参数（保持默认即可直接训练）"),

        Schema.union([
            Schema.object({
                network_algorithm: Schema.const("ia3").required(),
                ia3_train_on_input: Schema.boolean().default(false)
                    .description("是否在输入端应用 (IA)^3 缩放"),
            }),
            Schema.object({
                network_algorithm: Schema.union([
                    "lokr", "lora", "locon", "loha", "oft", "boft", "glora", "dylora", "tlora",
                ]).required(),
                network_dim: Schema.number().min(1).default(32)
                    .description("网络秩 Rank / Dim（默认 32；OFT/BOFT 时代表块大小）"),
                network_alpha: Schema.number().min(0).default(32)
                    .description("网络缩放权重 Alpha（默认 32）"),
            }),
        ]),

        Schema.object({
            batching: Schema.union(["tokens", "tokens_ffd", "count"]).default("tokens")
                .description("单步组批方式（tokens 按总 Token 容量自动打包多图；count 按固定图片张数）"),
        }),

        Schema.union([
            Schema.object({
                batching: Schema.const("count").required(),
                batch_size: Schema.number().min(1).default(4)
                    .description("每步训练图片张数（BATCH_SIZE）"),
            }),
            Schema.object({
                batching: Schema.union(["tokens", "tokens_ffd"]).required(),
                max_tokens: Schema.number().min(256).default(12288)
                    .description("单步最大 Token 容量（控制单步吞吐与显存占用；24GB 默认推荐 12288，显存不足可调低至 8192 或 6144）"),
                max_samples: Schema.number().min(0).default(0)
                    .description("单步最多打包图片张数上限；0 为不限制"),
            }),
        ]),

        Schema.object({
            grad_acc: Schema.number().min(1).default(1)
                .description("梯度累积步数（默认 1）"),
        }),
    ]),

    Schema.intersect([
        Schema.object({
            network_preset: Schema.union(["attn", "attn-mlp", "full-block", "all"]).default("attn-mlp")
                .description("训练模块覆盖范围（默认 attn-mlp 兼顾效果与体积；仅训练注意力层可选 attn）"),
        }).description("高级：LyCORIS 网络结构细项（保持默认即可）"),

        Schema.union([
            Schema.object({
                network_algorithm: Schema.const("lokr").required(),
                lokr_factor: Schema.number().min(-1).default(8)
                    .description("LoKr 分解因子（默认 8；设为 -1 自动按近似方阵拆分）"),
                lokr_full_matrix: Schema.boolean().default(false)
                    .description("对第二因子使用完整矩阵（full_matrix，开启后不再做低秩压缩，此时忽略 network_dim；默认关闭）"),
                lokr_decompose_both: Schema.boolean().default(false)
                    .description("同时对两个克罗内克因子做低秩分解（decompose_both，默认关闭）"),
                use_tucker: Schema.boolean().default(false)
                    .description("启用 Tucker 张量分解（默认关闭）"),
                rank_dropout_scale: Schema.boolean().default(false)
                    .description("按秩 Dropout 比例缩放输出（默认关闭）"),
            }),
            Schema.object({
                network_algorithm: Schema.union(["oft", "boft"]).required(),
                oft_constraint: Schema.number().default(0)
                    .description("正交变换约束系数（constraint，默认 0）"),
                oft_rescaled: Schema.boolean().default(false)
                    .description("启用重缩放正交变换（rescaled，默认关闭）"),
            }),
            Schema.object({
                network_algorithm: Schema.union(["lora", "locon", "loha"]).required(),
                use_tucker: Schema.boolean().default(false)
                    .description("启用 Tucker 张量分解（默认关闭）"),
                use_scalar: Schema.boolean().default(false)
                    .description("训练独立标量缩放因子（use_scalar，默认关闭）"),
                rank_dropout_scale: Schema.boolean().default(false)
                    .description("按秩 Dropout 比例缩放输出（默认关闭）"),
            }),
            Schema.object({
                network_algorithm: Schema.const("dylora").required(),
                dylora_block_size: Schema.number().min(1).default(4)
                    .description("DyLoRA 动态更新分块大小（block_size，默认 4）"),
            }),
            Schema.object({
                network_algorithm: Schema.const("tlora").required(),
                tlora_mask_min_rank: Schema.number().min(1).default(1)
                    .description("最小活跃秩（mask_min_rank，默认 1）"),
                tlora_mask_alpha: Schema.number().min(0).default(1.0)
                    .description("时间步掩码曲率指数（mask_alpha，默认 1.0）"),
                tlora_mask_max_timestep: Schema.number().min(1).default(1000)
                    .description("最大时间步跨度（mask_max_timestep，默认 1000）"),
            }),
            Schema.object({
                network_algorithm: Schema.const("glora").required(),
            }),
            Schema.object({}),
        ]),

        Schema.object({
            network_dora: Schema.boolean().default(false).description("启用权重幅度-方向分解 DoRA（默认关闭）"),
            network_dora_detach: Schema.boolean().default(false).description("DoRA 范数梯度截断（默认关闭）"),
            train_norm: Schema.boolean().default(false).description("同时训练归一化层 Norm（默认关闭）"),
            adapter_mode: Schema.union(["bypass", "merge"]).default("bypass")
                .description("适配器前向计算模式（默认 bypass；T-LoRA 仅支持 bypass）"),
            loraplus_ratio: Schema.number().min(0).default(1.0)
                .description("LoRA+ 上下矩阵学习率倍率；1.0 为关闭"),
            dropout_input: Schema.number().min(0).max(1).step(0.01).default(0)
                .description("输入端 Dropout 概率（默认 0）"),
            dropout_rank: Schema.number().min(0).max(1).step(0.01).default(0)
                .description("秩维度 Dropout 概率（默认 0）"),
            dropout_module: Schema.number().min(0).max(1).step(0.01).default(0)
                .description("模块级 Dropout 概率（默认 0）"),
        }),
    ]),

    Schema.object({
        lr_scheduler_mode: Schema.union(["cosine", "linear", "constant"]).default("cosine")
            .description("学习率衰减策略（默认 cosine 余弦退火）"),
        lr_warmup_steps: Schema.number().min(0).default(100)
            .description("学习率预热步数（须小于训练总步数，默认 100）"),
        lr_schedule_end: Schema.number().default(-1)
            .description("学习率衰减结束步数；-1 代表跟随训练总步数"),
        lr_min_value: Schema.number().min(0).max(1).step(0.01).default(0.1)
            .description("余弦退火终点最低学习率比例（默认 0.1）"),
        weight_decay: Schema.number().min(0).step(0.0001).default(0.01).description("权重衰减系数（默认 0.01）"),
        grad_clip: Schema.number().min(0).default(1.0).description("梯度裁剪上限；0 为关闭（默认 1.0）"),
        ema: Schema.number().min(0).max(0.9999).step(0.0001).default(0)
            .description("指数移动平均 EMA 系数；0 为关闭"),
        latent_cache: Schema.union(["online", "offline", "off"]).default("online")
            .description("图像 VAE 潜变量缓存模式（默认 online 自动边训边缓存落盘；offline 需预先缓存）"),
        text_cache: Schema.union(["online", "offline", "off"]).default("online")
            .description("文本特征缓存模式（默认 online 自动边训边缓存落盘；offline 需预先缓存）"),
        cache_dir: Schema.string().role("filepicker", { type: "folder" }).default("")
            .description("自定义预编码缓存目录；留空默认存放在 <数据集目录>/cache"),
        cache_dtype: Schema.union(["bf16", "fp8"]).default("bf16").description("预编码缓存保存精度（默认 bf16）"),
        save_minutes: Schema.number().min(0).default(0).description("按时间间隔额外保存（分钟）；0 为关闭"),
        keep_last: Schema.number().min(0).default(3).description("最多保留最近 N 个中间检查点（默认 3；0 为全部保留）"),
        max_train_epochs: Schema.number().min(0).default(0)
            .description("Epoch 备注字段（训练实际按 max_train_steps 步数停止）"),
        seed: Schema.number().min(0).default(0).description("全局训练随机种子"),
        log_every: Schema.number().min(1).default(10).description("控制台日志输出步数间隔（默认 10）"),
    }).description("高级：学习率调度、缓存与保存策略（保持默认即可）"),

    Schema.intersect([
        Schema.object({
            mixed_precision: Schema.union(["bf16", "fp16", "auto"]).default("bf16")
                .description("计算混合精度（默认 bf16）"),
            base_precision: Schema.union([
                "compute", "int8", "fp8", "fp8_compute", "mxfp8", "quant",
            ]).default("compute").description("冻结底模驻留精度（默认 compute 与计算精度一致；显存受限可选 fp8/int8）"),
            compile_mode: Schema.union(["off", "block", "model"]).default("off")
                .description("torch.compile 图编译模式（默认 off）"),
            tune_mode: Schema.union(["table", "off"]).default("table")
                .description("算子自动调优表（默认 table；Windows 环境缺少 C 编译器时会自动回退或手动改选 off）"),
            retune_steps: Schema.number().min(0).default(3)
                .description("前 N 步允许动态重调优（默认 3）"),
            parallel_mode: Schema.union(["none", "ddp", "fsdp", "pipeline", "threaded"]).default("none")
                .description("多卡并行策略（单卡及 Windows 环境保持 none）"),
            devices: Schema.string().default("0")
                .description("可见 GPU 集合内的本地编号，多卡用逗号分隔（如 0 或 0,1；none 仅一个编号）"),
        }).description("高级：底层精度、编译与多卡设置（保持默认即可）"),

        Schema.union([
            Schema.object({
                mixed_precision: Schema.union(["fp16", "auto"]).required(),
                fp16_fix: Schema.union(["online", "fp32_residual", "none"]).default("online")
                    .description("FP16 溢出修复（online 使用上游推荐 c=1/16；已带修复的单文件权重请选择 none）"),
            }),
            Schema.object({}),
        ]),
        Schema.union([
            Schema.object({
                parallel_mode: Schema.const("pipeline").required(),
                pipeline_schedule: Schema.union(["auto", "gpipe", "1f1b"]).default("auto")
                    .description("流水线调度（auto = 1f1b；需 tokens 组批、max_samples ≥ 1、离线文本缓存；自动使用 exact Token 预算）"),
            }),
            Schema.object({
                parallel_mode: Schema.const("threaded").required(),
                pipeline_schedule: Schema.union(["auto", "gpipe", "async"]).default("auto")
                    .description("线程流水线调度（auto = gpipe）"),
            }),
            Schema.object({}),
        ]),
        Schema.union([
            Schema.object({
                parallel_mode: Schema.union(["pipeline", "threaded"]).required(),
                microbatches: Schema.number().min(1).default(4)
                    .description("流水线微批次数（pipeline 时不得少于设备数；流水线需要 speed / auto、compute 底模精度，并关闭训练预览）"),
            }),
            Schema.object({}),
        ]),

        Schema.union([
            Schema.object({
                base_precision: Schema.union(["fp8", "fp8_compute", "mxfp8", "quant"]).required(),
                fp8_recipe: Schema.union(["row", "tensor", "block"]).default("row")
                    .description("FP8 动态缩放粒度（默认 row）"),
                fp8_dgrad: Schema.union(["fp8", "16bit"]).default("fp8")
                    .description("FP8 底模反向输入梯度精度（默认 fp8）"),
            }),
            Schema.object({}),
        ]),
    ]),
])

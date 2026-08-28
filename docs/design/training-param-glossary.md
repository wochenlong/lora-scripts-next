# 训练参数对照表（ui_key ↔ 各引擎原生字段）

> Issue #300 产物。目的：UI 展示统一词（ui_key + 中文 label），提交时由各引擎 adapter 查表写出原生字段。**不改上游参数名，只做展示与映射。**
> 列含义：`kohya` / `musubi` / `ai-toolkit` 列为该引擎**原生配置键**（ai-toolkit 列为 yaml 路径，省略 `config.process[0].` 前缀）。
> ⚠️ = 语义不等价，禁止硬并，adapter 必须显式处理（报错/警告/换算规则见 notes）。

## 核心可对齐项

| ui_key | 中文 label | kohya | musubi | ai-toolkit | notes |
| --- | --- | --- | --- | --- | --- |
| network_dim | 网络维度 (rank) | `network_dim` | `network_dim` | `network.linear` | |
| network_alpha | 网络 alpha | `network_alpha` | `network_alpha` | `network.linear_alpha` | |
| learning_rate | 学习率 | `learning_rate` | `learning_rate` | `train.lr` | UI 字符串（"1e-4"），adapter 转 float |
| lr_scheduler | 学习率调度器 | `lr_scheduler` | `lr_scheduler` | `train.lr_scheduler` | 各引擎可选值集合不同，UI 取交集 |
| optimizer_type | 优化器 | `optimizer_type`（AdamW8bit） | `optimizer_type` | `train.optimizer`（adamw8bit，小写） | adapter 大小写映射 |
| train_batch_size | 批量大小 | `train_batch_size` | `batch_size`（dataset 侧） | `train.batch_size` | musubi 落在 dataset toml |
| gradient_accumulation_steps | 梯度累加步数 | `gradient_accumulation_steps` | 同左 | `train.gradient_accumulation_steps` | |
| gradient_checkpointing | 梯度检查点 | `gradient_checkpointing` | 同左 | `train.gradient_checkpointing` | |
| seed | 随机种子 | `seed` | `seed` | `train.seed` | |
| max_grad_norm | 梯度裁剪阈值 | `max_grad_norm` | `max_grad_norm` | `train.max_grad_norm` | |
| output_dir | 模型保存文件夹 | `output_dir` | `output_dir` | `training_folder` | ⚠️ ai-toolkit 产物在 `training_folder/<name>/` 子目录 |
| output_name | 模型保存名称 | `output_name` | `output_name` | `config.name`（顶层） | |
| save_precision | 保存精度 | `save_precision`（bf16/fp16/float） | `save_precision` | `save.dtype`（bf16/float16/float32） | 取值表不同，adapter 映射 |
| trigger_word | 触发词 | （数据集概念/文件名） | — | `process.trigger_word` + caption 内 `[trigger]` 占位 | ⚠️ 作用域不同：kohya 数据集级，aitk 任务级 |
| sample_every_n_steps | 每 N 步采样 | `sample_every_n_steps` | 同左 | `sample.sample_every` | |
| sample_cfg | 采样 CFG | `sample_cfg`（UI） | `sample_cfg`（UI） | `sample.guidance_scale` | |
| sample_steps | 采样迭代步数 | `sample_steps`（UI） | 同左 | `sample.sample_steps` | |
| sample_width/height | 预览图宽高 | `sample_width/height`（UI） | 同左 | `sample.width/height` | |
| positive_prompts | 采样 Prompt | `sample_prompts` 文件 | 同左 | `sample.prompts`（内联数组） | ⚠️ 载体不等价：kohya/musubi 为文件路径（支持 --选项后缀），aitk 为内联字符串数组；adapter 负责剥选项后缀转数组 |

## ⚠️ 语义不等价项（显式标出，禁止硬并）

| ui_key | kohya | musubi | ai-toolkit | 规则 |
| --- | --- | --- | --- | --- |
| max_train_epochs / max_train_steps | epoch 优先，steps 可推导 | 同左 | **只有 `train.steps`** | aitk adapter：steps 直通；只给 epoch 报错并提示换算 |
| resolution | 单值字符串 "1024,1024" | `[w, h]` 二元组 | `resolution: [ints]` 多分辨率数组 | aitk adapter：取长边单值入数组，不伪造多分辨率 |
| save_every_n_epochs | 按轮保存 | 同左 | 无（`save.save_every` 仅步数） | aitk adapter：epoch 项警告忽略 |
| train_data_dir 布局 | 子目录 `重复次数_概念名` | 同 kohya（discover_subsets） | 平铺目录 + `datasets[].num_repeats` 字段 | aitk adapter：repeats 走 `dataset_repeats` 显式字段，不解析目录名 |
| mixed_precision | bf16/fp16/no | bf16（krea2 强制） | `train.dtype`（bf16 训练精度）+ `model.quantize` 量化 | 不同维度：aitk 省显存靠 quantize 而非 mixed_precision |
| caption_extension | `.txt`（带点） | 同左 | `caption_ext`（不带点，上游自补） | adapter 剥点 |
| shuffle_caption | `shuffle_caption` | `shuffle_tokens`（dataset） | `datasets[].shuffle_tokens` | |
| caption_dropout_rate | `caption_dropout_rate` | 同左 | `datasets[].caption_dropout_rate` | kohya 还有 caption_dropout_every_n_epochs，无对应 |

## 引擎专有项（不假统一，UI 按引擎显示）

**仅 AI Toolkit**：`quantize` / `quantize_te` / `qtype`（model.*，量化）、`low_vram`、`layer_offloading`、`use_ema`/`ema_decay`（train.ema_config）、`control_path`（datasets[]，图像编辑参考图目录列表，消费编辑数据集契约）。

**仅 musubi**：`fp8_base`/`fp8_scaled`（须成对）、`blocks_to_swap`、`turbo_dit` 系列、`timestep_sampling`/`discrete_flow_shift` 等调度细项。

**仅 kohya**：`clip_skip`、`v2`/`v_parameterization`、`network_dropout`、`dim_from_weights`、`noise_offset` 系列、dreambooth 的 `reg_data_dir` 等。

## 落点约定

- 各引擎 adapter 以本表为共享命名约定：UI schema 键（kohya 方言）→ 原生键的映射写死在 adapter 白名单内（参考 `mikazuki/engines/ai_toolkit/adapter.py` 与 `musubi/adapter.py` 的 SUPPORTED_FIELDS 模式）。
- 新引擎接入时必须新增本表对应列；找不到等价语的参数进「引擎专有项」，不发明第三套 UI 键名。
- 本表只约束**展示与落盘映射**，不约束上游默认值；各引擎 schema 默认值按上游推荐各自定。

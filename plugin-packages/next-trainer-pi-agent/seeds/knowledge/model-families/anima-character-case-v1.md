# Anima 角色 LoRA 实战案例 v1（AellaStella，anima-lora）

- Version: `2026-08-29`
- Scope: 单角色 OC 训练的真实完整参数案例（角色 AellaStella，页面 `anima-lora`，底模三元组 anima-base + qwen3-0.6B + qwen_image_vae，1024 分辨率）。
- Evidence status: **real local training run**（v1 案列完整参数原样保留）。与 `model-families/anima-lora-parameter-baseline.md`（v2 run）互为姊妹案例；两案差异见文末。本条是观察，不是因果结论。
- Aliases / 检索关键词: 角色案例, AellaStella, 完整参数, 实战, OC, character case, 参考配置

> 来源：用户真实训练案例 `AllaStella_anima_lora_character_params.toml`（案例机器路径 `E:\AI_Artwork\loraTraining\OC_lora\`）。本文件原被误放在 `pi-agent/knowledge/templates/`（工具不可见的遗留位置），2026-08-29 归并进知识库并补齐规范头。

## 完整参数（原案例值）

```toml
model_train_type = "anima-lora"
lora_type = "lora"
pretrained_model_name_or_path = "E:/RealTrainTest/resources/anima-base-V1.0.safetensors"
vae = "E:/RealTrainTest/resources/qwen_image_vae.safetensors"
qwen3 = "E:/RealTrainTest/resources/qwen_3_06b_base.safetensors"
qwen3_max_token_length = 512
t5_max_token_length = 512
timestep_sampling = "sigmoid"
sigmoid_scale = 1.0
discrete_flow_shift = 1.0
weighting_scheme = "uniform"
attn_mode = ""
split_attn = false
vae_disable_cache = false
unsloth_offload_checkpointing = false
train_data_dir = "E:/RealTrainTest/resources/_OC_Data_AellaStella"
reg_data_dir = ""
prior_loss_weight = 1.0
resolution = "1024,1024"
enable_bucket = true
min_bucket_reso = 512
max_bucket_reso = 2048
bucket_reso_steps = 64
bucket_no_upscale = false
output_name = "AellaStella_v1_anima_char"
output_dir = "E:/RealTrainTest/resources/lora_output"
save_model_as = "safetensors"
save_precision = "bf16"
save_every_n_epochs = 1
save_state = false
max_train_epochs = 32
train_batch_size = 2
gradient_checkpointing = true
gradient_accumulation_steps = 2
network_train_unet_only = true
network_train_text_encoder_only = false
learning_rate = 0.00003
unet_lr = 0.00003
text_encoder_lr = 0
lr_scheduler = "cosine_with_restarts"
lr_scheduler_num_cycles = 2
lr_warmup_steps = 100
loss_type = "l2"
optimizer_type = "pytorch_optimizer.CAME"
network_module = "networks.lora_anima"
network_dim = 32
network_alpha = 24
network_dropout = 0.05
dim_from_weights = false
train_norm = false
caption_extension = ".txt"
shuffle_caption = true
keep_tokens = 1
caption_dropout_rate = 0.02
caption_tag_dropout_rate = 0.05
prefer_json_caption = false
noise_offset = 0
multires_noise_iterations = 0
multires_noise_discount = 0.3
color_aug = false
flip_aug = false
random_crop = false
mixed_precision = "bf16"
full_fp16 = false
full_bf16 = false
fp8_base = false
fp8_base_unet = false
cache_latents = true
cache_latents_to_disk = true
cache_text_encoder_outputs = false
cache_text_encoder_outputs_to_disk = false
persistent_data_loader_workers = false
max_data_loader_n_workers = 0
enable_preview = true
positive_prompts = "AellaStella, 1girl, solo, looking at viewer, upper body, simple background"
negative_prompts = "worst quality, low quality, lowres, blurry, jpeg artifacts, bad anatomy, bad hands, text, watermark, signature, artist name"
sample_width = 1024
sample_height = 1024
sample_cfg = 4.5
sample_seed = 42
sample_steps = 40
sample_sampler = "euler"
sample_scheduler = "simple"
sample_at_first = true
sample_every_n_epochs = 4
log_with = "tensorboard"
logging_dir = "E:/RealTrainTest/resources/lora_logs"
seed = 3139060772
```

## 关键设计点（复用/调整依据）

- **底模三元组**：anima-base + qwen3 0.6B + qwen_image_vae 必须成套；token 长度各 512。
- **网络**：`networks.lora_anima`，dim=32 / alpha=24 / dropout=0.05；只训 UNet（`network_train_unet_only = true`，`text_encoder_lr = 0`）。
- **学习率**：3e-5 + CAME + cosine_with_restarts(cycles=2) + warmup 100 —— 本案例的默认起点；图少(<20)可降至 1e-5，图多/风格复杂可试 5e-5（推断层，需验证）。
- **训练量**：32 epochs × batch 2 × grad_accum 2；经验区间"总曝光量 ≈ 数据集张数 × 20~40 倍"。
- **数据**：1024 基准 + 分桶（512~2048，步长 64）；cache_latents 落盘。
- **caption**：txt 同后缀；shuffle + tag_dropout 0.05 + keep_tokens=1（保留触发词）；角色触发词放 positive_prompts 首位。
- **精度**：bf16 全链，fp8 全关（质量优先的保守配置）。
- **采样**：1024、cfg 4.5、euler/simple 40 步、每 4 epoch 预览 —— 用于观察过拟合拐点。

## 与 v2 run 的已知差异（观察，非因果结论）

| 字段 | v1（本案例） | v2（`anima-lora-parameter-baseline.md`） |
|---|---|---|
| timestep_sampling / discrete_flow_shift | `sigmoid` / 1.0 | `shift` / 3 |
| max_train_epochs | 32 | 36 |
| sample_cfg | 4.5 | 4 |
| lr warmup | 100 | 50（cosine_with_restarts 2 cycles 同） |

## 复用规则（Agent 起草时必须遵守）

1. 所有 `E:/RealTrainTest/...` 是案例机器路径，**必须替换**为用户机器上真实存在的路径；替换不了就问用户，不得照抄。
2. `output_name` 按角色名+版本重命名；`positive_prompts` 的角色触发词换成目标角色 token；其余 prompt 结构（质量词/负面词）可保留。
3. 本模板是"已验证起点"，不是唯一正确答案；偏离值域（如 network_dim>64、lr>1e-4）必须显式提示风险。
4. 起草后仍须走 `training_config_validate` → 用户确认 → `training_config_commit` 全流程；案例不替代任何校验。

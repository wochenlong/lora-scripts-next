# Anima Edit 显存与训练分辨率参考

> **状态**：汇总仓库内已有设计、配置与开发记录；**不含**系统化双参考 vs 单参考对照 benchmark。  
> **分支**：`anima-edit`  
> **关联**：[anima-edit-multi-reference.md](anima-edit-multi-reference.md)、[anima-training.md](../anima-training.md#图像编辑--条件训练实验)

## 1. 结论速览

| 模式 | DiT 输入时间维 `T` | 仓库内**训练分辨率**主流取值 | 显存数据现状 |
|------|-------------------|------------------------------|--------------|
| **单张参考图** | `T=2`（噪声 1 + 参考 1） | **512**（展示/表情/ImagePulse 示例）；**1024**（`anima-edit-reference.toml` 真实 50 epoch 探针） | 开发记录：24GB 卡上 **1024 + full cache** 首 step 峰值约 **22.9GB**（见 §4） |
| **双张参考图** | `T=3`（噪声 1 + 参考 2） | **512**（P0 冒烟与全部 `*-dual-*` / `edit3` 示例） | **无**同配置下单/双对照实测；设计上 1024 留到 512 冒烟通过后 |

**实用建议（在缺少双参考 1024 实测前）：**

- 24GB：单参考可尝试 **1024**（`gradient_checkpointing` + `cache_latents` + `cache_text_encoder_outputs`，与示例一致）；双参考建议从 **512** 起步。
- 16GB 及以下：优先 **512**；单/双参考均开启梯度检查点与 TE/VAE 缓存；必要时沿用 Anima 文生图 LoRA 的 `blocks_to_swap`（见 §5）。
- 训练预览默认可 **512**（`anima-edit-lora` / API），与训练分辨率独立；manifest 里 `width`/`height` 可 512 训 + 1024 预览（见 `anima-training.md` ImagePulse 说明）。

---

## 2. 机制：为什么双参考更吃显存

Anima Edit 在 conditioning 模式下把参考图 VAE latent 沿 **时间维 `dim=2`** 与噪声 latent 拼接后送入 DiT（见 `vendor/sd-scripts/anima_train_network.py`）：

```text
单参考：  [B, C, T=2, H, W]  =  noisy(1) + ref1(1)
双参考：  [B, C, T=3, H, W]  =  noisy(1) + ref1(1) + ref2(1)
```

相对单参考，双参考在 **同一训练分辨率** 下：

1. **前向激活**：多 1 帧参考 latent，DiT 侧序列长度 +50%（仅指拼接维，非整卡显存 +50%）。
2. **Latent 缓存**：`cache_latents` 时每样本多缓存 1 份参考 latent（双参考子目录 2 张图均编码）。
3. **预览**：manifest 方案 B 可带 ref1/ref2 元数据；训练步显存与单参考预览相近，但生成预览时仍按 manifest 分辨率采样。

显存与分辨率仍近似 **平方律**：`512→1024` 边长 ×2，单帧 latent 面积约 ×4；条件帧数从 1→2 再叠乘约 **1.5×** 条件侧输入（`T=2→T=3`）。

---

## 3. 仓库内配置与分辨率对照表

### 3.1 单张参考图

| 来源 | 训练 `resolution` | `max_bucket_reso` | 备注 |
|------|---------------------|-------------------|------|
| WebUI 默认 `anima-edit-lora.ts` | `512,512` | 2048 | 文案：P0 冒烟推荐 512，正式可改 1024 |
| `apply_anima_training_defaults` | 空则填 `512,512` | — | `mikazuki/app/api.py` |
| `anima-edit-single-ref-12epoch.toml` | 512 | 1024 | 32 对 showcase，12 epoch |
| `anima-edit-expression-*-epoch.toml` | 512 | 1024 | ImagePulse 表情子集 |
| `anima-edit-reference.toml` | **1024** | 2048 | 脱敏 50 epoch 真实探针配置 |
| `anima-edit-dataset.toml` | **1024** | — | 通用 dataset 模板 |
| 预览 manifest 示例 | — | — | `width`/`height` 多为 **512** |

### 3.2 双张参考图

| 来源 | 训练 `resolution` | `conditioning_multi_reference` | 备注 |
|------|---------------------|--------------------------------|------|
| [anima-edit-multi-reference.md](anima-edit-multi-reference.md) §2.2 | **512×512**（P0） | true | 正式 1024 **延后** |
| `anima-edit-dual-ref-smoke.toml` | 512 | dataset TOML | 2 step 冒烟 |
| `anima-edit-dual-ref-10epoch.toml` | 512 | true | |
| `anima-edit-showcase-dual-*.toml` | 512 | true | 文档例图流程 |
| `data/edit3` 冒烟 | 512 | true | `script/ops/prepare_edit3_multi_ref.py` |

### 3.3 公共训练参数（单/双参考示例一致）

以下在 `docs/examples/anima-edit-*.toml` 中反复出现，影响显存基线：

| 参数 | 典型值 | 显存影响 |
|------|--------|----------|
| `train_batch_size` | 1 | 无法再降（除梯度累积） |
| `gradient_checkpointing` | true | 显著降低激活显存 |
| `cache_latents` | true | 训练步释放 VAE；磁盘/内存换显存 |
| `cache_text_encoder_outputs` | true | 训练步释放 Qwen3 |
| `network_train_unet_only` | true | 不训 TE |
| `mixed_precision` | bf16 | |
| `optimizer_type` | AdamW8bit | |
| `network_dim` / `alpha` | 4 / 4（示例）或 16 / 16（schema 默认） | rank 越高略增显存 |
| `vae_chunk_size` | 64 | 降 VAE 峰值 |
| `vae_disable_cache` | true | 降 VAE 峰值 |
| `sample_at_first` | false（conditioning 强制） | 避免 step 0 双份采样 |

conditioning 模式下 WebUI/API 会强制 `cache_latents` + `cache_text_encoder_outputs`（`api.py` `apply_anima_training_defaults`）。

---

## 4. 已有实测与观测记录

### 4.1 单参考 · 1024 · 24GB 卡（开发会话记录）

在 conditioning 训练接入阶段，**单参考**、开启 latent + TE 缓存后，首 training step 曾观测到：

- GPU 利用率 ~100%
- 显存约 **22.9GB / 24GB**
- 首 step 在部分配置下极慢或看似卡住（与缓存冷启动、显存压力有关）

配置语境：`resolution` 为 **1024** 量级、`train_batch_size=1`、`gradient_checkpointing=true`、conditioning 缓存路径修复前后均有尝试。  
**未**在仓库中落盘为可复现的 benchmark 脚本或日志文件。

### 4.2 双参考 · 512 冒烟（验收标准，非显存数字）

[anima-edit-multi-reference.md](anima-edit-multi-reference.md) 定义的 P0 验收：

- 512、`gradient_checkpointing`、极小数据集
- 能跑通 step / 1～2 epoch，无 shape/OOM
- **未要求**记录峰值 GB

`anima-edit-dual-ref-smoke.toml` + `data/edit3` 对应该路径；仓库 **无** `output/` 下留存训练日志。

### 4.3 文生图 Anima LoRA（非 Edit，仅供参考）

README / README-zh 中 **Anima 文生图 LoRA @ 1024**、RTX 4090 分级（**非** conditioning，**非** Edit）：

| 显存 | 建议配置 |
|------|----------|
| ≥ 24 GB | 默认 |
| ≥ 16 GB | `gradient_checkpointing` |
| ≥ 12 GB | 梯度检查点 |
| ≥ 10 GB | + `blocks_to_swap=16` |
| ≥ 8 GB | swap 24 + 缓存 TE + LoKr |

Edit 模式在相同分辨率下应 **高于或接近** 文生图（多 1～2 帧参考 latent + 参考 latent 缓存），**不能**直接套用该表为 Edit 保证值。

---

## 5. 显存优化手段（与模式无关）

来自 `vendor/sd-scripts/docs/anima_train_network.md` 与 WebUI schema，单/双参考均可考虑：

| 手段 | 说明 |
|------|------|
| 降低 `resolution` | 512 vs 1024 影响最大 |
| `gradient_checkpointing` | 默认已开 |
| `cache_latents` / `cache_text_encoder_outputs` | Edit 默认强制 |
| `split_attn` | schema 有项，降 attention 显存、变慢 |
| `blocks_to_swap` | Anima DiT 块 CPU 交换（文生图表有分级） |
| `unsloth_offload_checkpointing` | 与 swap 互斥 |
| Adafactor | 略省显存于 AdamW8bit |
| 降低 `network_dim` | 示例多用 4，UI 默认 16 |
| 关闭训练预览或降低预览分辨率 | 减轻 epoch 末采样峰值 |
| `train_batch_size=1` + `gradient_accumulation_steps` | 模拟大 batch |

双参考在 **1024** 若 OOM：设计文档建议先记录 OOM，再 **降分辨率或减参**（[anima-edit-multi-reference.md](anima-edit-multi-reference.md) 验收表）。

---

## 6. 分辨率策略建议

```text
                    单参考                          双参考
              ┌─────────────────┐           ┌─────────────────┐
  探索/冒烟   │ 512（示例默认）  │           │ 512（P0 强制）   │
              ├─────────────────┤           ├─────────────────┤
  正式训练    │ 1024（探针验证） │           │ 1024（待验证）   │
              │ 需 ≥24GB 或优化  │           │ 建议 512 稳定后  │
              └─────────────────┘           └─────────────────┘
  预览        │ 可与训练不同；manifest 512 或 1024 │
              └──────────────────────────────────┘
```

- **数据准备**：AISP/出图常用 **1024** 方图（`script/scratch/aisp-*.json`），训练前需 **resize 到训练分辨率** 或依赖 bucket。
- **Bucket**：示例普遍 `enable_bucket=true`，`max_bucket_reso` 1024（512 训练）或 2048（1024 训练）；实际 bucket 由 target 图尺寸与 `resolution` 共同决定。

---

## 7. 数据缺口与建议补测

当前仓库 **缺少** 下列结构化数据，本文无法给出「双参考 1024 需要 XX GB」的确定值：

| 待测项 | 建议方法 |
|--------|----------|
| 单参考 @ 512 峰值显存 | 同机跑 `anima-edit-single-ref-12epoch.toml` 1～2 step，读训练监控或 `nvidia-smi` |
| 双参考 @ 512 峰值显存 | `anima-edit-dual-ref-smoke.toml`，对比单参考同分辨率 |
| 单 vs 双 @ 1024 | 仅在 24GB+ 尝试；记录是否 OOM |
| 预览开启时的峰值 | `sample_every_n_epochs=1` vs 关闭 |

建议在 `output/<run>/` 或训练监控中记录：`resolution`、`edit_reference_layout` / `conditioning_multi_reference`、`gpu_memory_used_mb` 峰值，并回写本节。

---

## 8. 引用索引

| 文档 / 路径 | 内容 |
|-------------|------|
| [anima-edit-multi-reference.md](anima-edit-multi-reference.md) | 双参考 P0：512 冒烟、显存约定 |
| [anima-training.md](../anima-training.md) | Edit 入口、示例索引 |
| [anima-edit-reference.toml](../examples/anima-edit-reference.toml) | 1024 单参考长训参考 |
| [anima-edit-dual-ref-smoke.toml](../examples/anima-edit-dual-ref-smoke.toml) | 512 双参考冒烟 |
| [anima-edit-single-ref-12epoch.toml](../examples/anima-edit-single-ref-12epoch.toml) | 512 单参考 showcase |
| `mikazuki/schema/anima-edit-lora.ts` | UI 默认 512、参考布局 |
| `README-zh.md` | 文生图 Anima LoRA 1024 / 4090 分级（非 Edit） |

---

| 日期 | 说明 |
|------|------|
| 2026-05-27 | 初版：汇总配置与开发观测；标明无双参考显存 benchmark |

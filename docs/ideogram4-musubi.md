# Ideogram 4（Musubi-Tuner）训练指南

Ideogram 4 通过 **Musubi-Tuner** 引擎接入，训练入口：训练页选择 **模型 = Ideogram 4，引擎 = Musubi-Tuner，目标 = LoRA**，或直接访问 `/lora/ideogram4.html`。

当前支持 **LoRA 训练**；上游尚未支持全量微调，也 **不支持把 LoRA 合并回 FP8 底模**。

## 许可与权重（务必先读）

- 模型许可为 **Ideogram Non-Commercial**：仅限非商业用途，微调同样受此限制；禁止使用其输出训练与 Ideogram 竞争的模型。
- 官方仅发布 **量化权重（FP8 / NVFP4）**，没有 BF16/FP16 底模。DiT 始终以预量化 FP8 加载作为冻结基座，LoRA 以计算精度运行——这是唯一的工作模式，不是可选项。
- 本项目的整合包 **不预置这些权重**。请在「训练用模型」区下载或手动放置，组件取自 Comfy-Org 单文件布局：

| 组件 | 文件 |
| --- | --- |
| conditional DiT | `ideogram4_fp8_scaled.safetensors` |
| unconditional DiT（非对称 CFG，可选） | `ideogram4_unconditional_fp8_scaled.safetensors` |
| 文本编码器（Qwen3-VL-8B，FP8） | `qwen3vl_8b_fp8_scaled.safetensors` |
| VAE（Flux2） | `flux2-vae.safetensors` |
| tokenizer（Qwen3-VL-8B） | 目录，建议本地放置 |

默认路径：`sd-models/ideogram4/`，tokenizer 目录为 `sd-models/ideogram4/qwen3-vl-8b-tokenizer`。

### 需要多少磁盘空间

官方只发量化权重，**有 FP8 版本，而且 FP8 就是我们默认使用、也是 musubi 训练脚本唯一支持的加载格式**。Comfy-Org 镜像上主要的文件体积（2026-10 实测）：

| 文件 | 体积 | 是否必需 |
| --- | --- | --- |
| `ideogram4_fp8_scaled.safetensors`（conditional DiT） | 8.64 GB | 必需 |
| `qwen3vl_8b_fp8_scaled.safetensors`（Qwen3-VL-8B 文本编码器） | 9.86 GB | 必需 |
| `flux2-vae.safetensors` | 0.31 GB | 必需 |
| tokenizer（Qwen3-VL-8B 目录） | 约 0.02 GB | 必需 |
| `ideogram4_unconditional_fp8_scaled.safetensors` | 8.64 GB | 可选（非对称 CFG 推理 / 显式开启的训练采样） |

镜像里还有 **NVFP4**（DiT 5.11 GB + 文本编码器 5.87 GB）与 **int8_convrot**（8.93 GB）变体，体积更小；我们的默认资源清单与上游文档都按 FP8 单文件路径配置，其它量化格式 **未做过验证**。

配套空间按需预留：

- **权重最低要求**：约 **18.8 GB**（必需四项）；需要无条件 DiT 再 +8.6 GB（合计约 27.5 GB）。
- **文本缓存**：每 token 存 53248 通道——BF16 下 128 token ≈ 13.6 MB/图，1000 张约 **13.6 GB**；`text_cache_dtype=fp8_e4m3fn` 可减半。
- **latent 缓存**：每图 MB 级，可忽略。
- **引擎环境**：若本机还没装 musubi-tuner（含 torch 等），安装另需约 **8–12 GB**。

**建议预留 60–80 GB**（权重 + 一份缓存 + 引擎与产物余量）；已有 musubi 环境且数据集只有几百张图时，40 GB 也够。下载期间会同时在目标目录写入一份文件，不要贴着剩余空间下限操作。


## 运行流程与显存

训练按三阶段任务组执行：**缓存 latents → 缓存文本编码器输出 → 训练**。缓存阶段固定使用第一张 GPU。

- **文本缓存很大**：每个 token 存 53248 通道，BF16 下 128 token ≈ 13.6 MB/图（1k 图 ≈ 13.6 GB），256 token 翻倍，512 token ≈ 54.5 GB。可把 `text_cache_dtype` 设为 `fp8_e4m3fn` 减半，但属于精度权衡。
- 基座为 9.3B FP8 DiT + Qwen3-VL-8B 文本编码器。显存不足时按顺序尝试：`blocks_to_swap`（上限 **33**）、`gradient_checkpointing`、关闭训练中采样预览。
- 预检会在显存低于 16 GB 时提示，并检查已安装的 musubi-tuner 快照是否包含 Ideogram 4 脚本；缺失时请在「设置 → 训练引擎」修复/重装。

## 参数要点

- **时间步采样**：默认 `ideogram4_shift`（官方对齐的分辨率感知采样器），通常无需修改。上游另有 `ideogram4_timestep_mu/std` 两个兼容参数，但明确忽略其取值，界面不提供。
- **损失**：纯 MSE flow matching，`weighting_scheme` 只能是 `none`（界面不提供该选项，导入其它值时会被忽略并提示）。
- **caption**：官方用结构化 JSON（`high_level_description` / `style_description` / `compositional_deconstruction`）。纯文本也能训练；开启 `validate_caption_structure` 会校验结构，配合 `warn_on_caption_issues` 可只警告不中断。
- **LoRA 目标**：仅训练 conditional transformer（`attention.qkv`、`attention.o`、`feed_forward.w1/w2/w3`）。
- **注意力**：`sdpa` / `flash_attn` / `xformers` 可用；**SageAttention 不可用**（head 维度 256 超出其 int8/fp8 核支持范围）。
- 精度：`mixed_precision` 仅 bf16；`dit_dtype` 默认 bfloat16（底模始终 FP8 加载）。

## 训练中采样

- 需要同时给出 `text_encoder` 与 `vae` 路径。
- 采样调度由 `sampler_preset` 决定：`V4_DEFAULT_20`（18+2 步，默认）、`V4_QUALITY_48`（45+3 步）、`V4_TURBO_12`（11+1 步）；`initial_sigma` 默认 1.004。
- 默认只用 conditional DiT 采样（LoRA 只挂在 conditional DiT 上）。若要使用官方非对称 CFG，需要提供 unconditional DiT 并开启对应开关。
- 官方结构化 JSON prompt 也可用于采样，界面默认给出一个三键示例。

## 本仓的上游补丁

我们固定的上游快照（2026-08-13）中，`ideogram4_utils.py` 的文本编码器加载在 `to_empty()` 之后 **没有重建 rotary embedding**，非持久化的 `inv_freq` 缓冲会保持未初始化，导致文本缓存是垃圾值。上游在 v0.3.6 修复。本仓不升级 pin，而是在启动训练前对该文件打等价补丁（幂等、写入前做语法校验），同时把 tokenizer 指向本地目录以支持离线运行。

## 已知限制

- 上游标注该模型支持为 **experimental**；上游 issue 报告过文本编码器预缓存阶段 OOM 与 resume 变慢，长训练前请先小步验证。
- 只能 LoRA；LoRA 不能合并回 FP8 权重，生成时通过 forward hook 加载，结果可能与把 LoRA 合并进权重的工具（如 ComfyUI）不同。
- 真机验收（3 步冒烟 + 缓存复用）在 [#424](https://github.com/wochenlong/lora-scripts-next/issues/424) 跟踪。

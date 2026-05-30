# Anima LoRA 训练指南

## 进入训练页面

启动 WebUI 后，左侧 sidebar 点 **Anima LoRA** 进入。

> 技术细节：该页面复用了原 SD3 的 URL 槽位（`/lora/sd3.html`），但参数集合与训练脚本已完全是 Anima。

## 下载 Anima 模型

Anima 训练需要三个权重文件（DiT、Qwen3 文本编码器、VAE）。**整合包**根目录或**源码 clone 根目录**均可双击：

```text
Download-Anima-Model.bat
```

脚本会从 ModelScope（`circlestone-labs/Anima`）下载到相对路径 **`sd-models/anima/`**，已存在的文件会自动跳过。也支持放在整合包根目录（与 `run_gui.bat` 同级）或 `SD-Trainer/` 内（与 `gui.py` 同级）。

## 模型路径

表单里需要填以下模型路径：

| 字段 | 含义 |
|------|------|
| `pretrained_model_name_or_path` | Anima DiT 主权重，如 `./sd-models/anima/anima-base-v1.0.safetensors` |
| `vae` | Qwen Image VAE 模型路径（必填） |
| `qwen3` | Qwen3 文本模型，可填 `.safetensors` / `.pt` 文件，或完整本地模型目录 |
| `t5` | T5 文本编码器权重 |

## 训练类型

- **LoRA** — 默认训练类型，适合大多数场景
- **LoKr** — 使用 LyCORIS 后端（`lycoris.kohya` + `algo=lokr`），支持 CP 分解、DoRA 等高级参数
- **T-LoRA** — 时间步动态 LoRA，根据扩散时间步自动调整 rank，配合正交初始化防止过拟合（详见下方教程）

## 预览图生成

打开表单里的 **`enable_preview`** 开关后，采样会切到 Anima 推荐参数：
- 分辨率：1024×1024
- CFG：4.5
- 步数：40
- Seed：42
- 自动填入 Anima 风格的正反向提示词

## 训练步数经验值

在同一套数据与分辨率下，**约 1000–3000 次优化步** 往往已能呈现可用的角色外观。实际所需步数随素材量、repeat、网络维度、学习率变化很大，请以验证图为准。

**`num batches per epoch`** × **目标 epoch** ≈ 累计步数（例如每 epoch 510 batch → 第 2 个 epoch 结束约 1020 步）。

## 后端架构

本地入口 [`scripts/dev/anima_train_network.py`](../scripts/dev/anima_train_network.py) 是兼容 wrapper：它适配 GUI 生成的 TOML，并委托给 `vendor/sd-scripts` 中的 kohya-ss 后端执行训练。

配置文件：[`config/anima_backend.toml`](../config/anima_backend.toml)

## 进阶：T-LoRA 训练教程

### 什么是 T-LoRA？

T-LoRA（Timestep-Dependent LoRA）是一种改进的 LoRA 方法。普通 LoRA 对所有扩散时间步使用相同的 rank，而 T-LoRA 会**根据当前时间步动态调整有效 rank**——噪声大的时间步使用更高 rank（需要更多表达能力），噪声小的时间步使用更低 rank（避免过拟合细节）。

**优点**：
- 更高效地利用参数，相同 rank 下能学到更多信息
- 正交初始化减少训练早期的不稳定性
- 适合需要精细控制的训练场景

**适合场景**：
- 数据集较小、容易过拟合时
- 希望在不增加模型体积的前提下提升训练效果

### 快速开始

1. 在 Anima LoRA 训练页面，找到「**网络类型**」下拉菜单
2. 选择 **T-LoRA**（排在 LoRA、LoKr 之后）
3. 其他参数照常填写，点击开始训练

选择 T-LoRA 后，系统会自动切换到 T-LoRA 专用的网络模块，并使用优化过的默认参数。

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **网络维度 (network_dim)** | 32 | T-LoRA 的动态 rank 会压缩有效容量，因此通常需要比普通 LoRA 更高的 dim |
| **网络 Alpha (network_alpha)** | 32 | 建议与 network_dim 保持一致，避免学习率被意外缩放 |
| **最小 Rank (tlora_min_rank)** | 4 | 时间步接近 0 时使用的最低 rank。越小越节省参数但容量越低 |
| **Rank 调度 (tlora_rank_schedule)** | linear | rank 随时间步变化的方式。`linear` 为线性插值，`cosine` 更平滑 |
| **正交初始化 (tlora_orthogonal_init)** | 开启 | 用正交矩阵初始化权重，训练更稳定，建议保持开启 |
| **UNet 学习率 (unet_lr)** | — | 由于动态 rank 使得有效梯度更小，可能需要比普通 LoRA 适当提高 |

### 与普通 LoRA 的区别

| | LoRA | T-LoRA |
|---|------|--------|
| Rank | 固定（如 16） | 动态（min_rank ~ network_dim） |
| 收敛速度 | 较快 | 较慢（需要更多步数） |
| 过拟合风险 | 较高 | 较低（低噪声步用低 rank） |
| network_dim | 通常较小即可 | 通常需要更大 |
| 模型体积 | 取决于 dim | 与同 dim 的 LoRA 相同 |

### 常见问题

**Q: T-LoRA 训练很慢，预览图变化不大？**

这是正常的。T-LoRA 的动态 rank 机制会在低噪声时间步降低有效容量，导致收敛比普通 LoRA 慢。可以尝试：
- 增大 `network_dim`
- 增大 `tlora_min_rank`
- 适当提高学习率
- 确保 `tlora_orthogonal_init` 开启
- 耐心多训几个 epoch，T-LoRA 的优势会在后期体现

**Q: T-LoRA 的模型文件可以直接用普通 LoRA 加载吗？**

可以。T-LoRA 的模型权重格式与普通 LoRA 兼容，推理时使用完整 rank（不做时间步动态调整），可以在任何支持 LoRA 的推理工具中正常加载。

**Q: 使用 Automagic / CAME 训练时 loss 变成 NaN？**

优先确认 PyTorch 版本 ≥ 2.5，并避免开启 `full_bf16` / `full_fp16`。Anima 页面仍可使用 `mixed_precision=bf16`，但可训练 LoRA 权重建议保持 FP32；后端会在 `Automagic` 和 `pytorch_optimizer.CAME` 下自动关闭 full 半精度训练，以降低 NaN 风险。不要把 bf16 改成 fp16 作为绕过方案；fp16 数值范围更窄，通常只会让 NaN 晚几步出现。支持 bf16 的显卡上，后端会把这两个优化器的 Anima fp16 配置自动改回 bf16。

**Q: T-LoRA 和 LoKr 哪个好？**

两者解决不同的问题：
- **LoKr** 适合需要高秩、高稀疏度的场景（如 Dense Attention 模型），参数效率更高
- **T-LoRA** 适合需要防止过拟合的场景，通过动态 rank 自适应不同扩散阶段的需求

可以根据实际训练效果选择，也可以都试试对比。

---

## 进阶：LoKr 训练参数参考

对于 Anima 这样的图像模型，由于其 Attention 矩阵是 Dense（高秩）的，传统的 LoRA（低秩）可能在表达能力上存在瓶颈。**LoKr (Kronecker product) 天生适合这种需要高秩、高稀疏度的场景**。

> 以下参数仅供参考，实际效果因数据集、训练目标和硬件环境而异，建议根据自己的情况调整。

1. **起步参数**：
   - `factor` 从较大值（如 `16`）开始尝试
   - LoKr 通常比 LoRA 更耐受较高的学习率，可以在默认值基础上适当提高，观察收敛情况

2. **`full_matrix` 模式**：
   - 开启后 LoKr 使用完整 Kronecker 乘积而非低秩近似，不再需要设置很大的 `dim`
   - 适合希望最大化 LoKr 表达能力的场景

3. **效果不佳时的调整方向**：
   - 逐步降低 `factor`，降低 factor 意味着增加参数量、提升表达能力
   - 降低 `factor` 的同时建议相应降低学习率，避免过拟合
   - `factor` 越小参数量越大，过小时接近全量微调

4. **混合训练**：
   - LoKr 与 LoRA 的性质互补，如果单独使用效果不理想，可以尝试两者结合训练

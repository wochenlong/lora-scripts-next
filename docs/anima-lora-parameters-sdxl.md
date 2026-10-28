# Anima LoRA 主要参数说明（写给 SDXL 用户）

如果你已经会用 SDXL 训 LoRA，换到 Anima 时很多习惯还能沿用，但有几处**必须改过来**，否则容易白跑一趟。

本文只讲**真正会影响出图效果**的参数；下载模型、点哪里开训等完整流程，请看 [Anima LoRA 训练指南](./anima-training.md)。

在 WebUI 里打开：**Anima LoRA → 标准模式**。下面各节标题与页面上的分组名称一致，方便对照填写。

---

## 和 SDXL 有什么不同？

下面这张表帮你快速对齐：左边是你可能已经熟悉的 SDXL 做法，右边是 Anima 里对应的设置。

| 你在 SDXL 里可能这样 | 换到 Anima 后 | 小贴士 |
|----------------------|---------------|--------|
| 只选一个底模文件 | 要准备 **主模型（DiT）**、**VAE**、**Qwen3** 三个路径 | 少填任何一个都开不了训 |
| 用 CLIP-L / CLIP-G | 改用 **Qwen3** 读提示词，训练里还有 **T5** 一路 | 默认只训主网络，不用特意去训文本编码器 |
| 会调 `clip_skip` | **没有这项** | 别从旧配置里照搬过来 |
| 分辨率常用 512 或 1024 | 默认建议 **1024×1024** | 人物 LoRA 更推荐 1024；分桶（bucket）照样能用 |
| 标签多是 `.txt` 逗号分隔 | **更推荐 JSON 标签** | 继续用 `.txt` 也行，但 JSON 往往更稳 |
| 预览 CFG 7、步数 20 左右 | 预览建议 **CFG 4–5**、**步数 30–50** | 预览和 SDXL 不一样，不代表训练坏了 |
| `network_dim` 常用 16 | 16 仍然好用 | 若用 LoKr、T-LoRA，规则另说，见 [训练指南](./anima-training.md) |
| 勾选 xformers | **Attention 模式留空** 让系统自动选 | Anima 页面没有 SDXL 那套 xformers 开关 |

**小结**：先把**模型路径、分辨率、标签、学习率、LoRA 维度**配对，再考虑动 Anima 专有的时间步相关选项。多数情况下，前面几项对了，训练就能顺利跑起来。

---

## 想调什么效果，该改哪里？

| 你想达到的效果 | SDXL 里常动什么 | Anima 里对应改什么 |
|----------------|-----------------|-------------------|
| 更像角色 / 更贴画风 | 素材质量、触发词、训练轮数 | 同上，另外注意 **JSON 标签是否写全** |
| 画面更清晰 / 尺寸 | 分辨率、分桶 | `resolution`（默认 `1024,1024`）、`enable_bucket` |
| 训得更久 / 更猛 | epoch、batch | 一样；总步数 ≈ 每轮 batch 数 × 轮数 |
| LoRA 容量大小 | `network_dim`、`network_alpha` | 标准 LoRA 用法相同 |
| 学太快、过拟合 | 学习率、轮数 | `unet_lr`、优化器；**Automagic 不能当普通 AdamW 用** |
| 显存不够 | batch、梯度检查点、缓存 | `gradient_checkpointing`、`cache_latents`、`cache_text_encoder_outputs` |
| 预览图不像预期 | CFG、步数 | `sample_cfg` 约 4.5、`sample_steps` 约 40（只影响预览） |

---

## 1. 模型路径（三项都要填）

Anima 不像 SDXL 只选一个 ckpt，页面上有三项**必填**：

| 页面上的参数 | 是什么 | 和 SDXL 比 |
|--------------|--------|------------|
| `pretrained_model_name_or_path` | Anima **主模型（DiT）** | 类似你以前选的底模 / U-Net 权重 |
| `vae` | **Qwen Image VAE** | SDXL 有时合在包里；Anima **必须单独指定** |
| `qwen3` | **Qwen3** 文本模型 | 负责读你的提示词，角色类似 CLIP，但不是 CLIP |

整合包用户可在根目录运行 `Download-Anima-Model.bat`，文件会下到 `sd-models/anima/`。路径说明见 [训练指南 · 模型路径](./anima-training.md#模型路径)。

### 文本编码器相关（容易搞混）

| 参数 | 默认 / 建议 | 对你有什么影响 |
|------|-------------|----------------|
| `qwen3_max_token_length` | 512 | 标签太长会被截断；一般不用改 |
| `t5_max_token_length` | 512 | T5 一路的 token 上限 |
| `network_train_unet_only` | **开启** | **只训主网络**；训人物、风格 LoRA 保持开启即可 |
| `network_train_text_encoder_only` | 关闭 | 只有当你**刻意要训 Qwen3** 时才开 |
| `t5_tokenizer_path` | 留空 | 用内置即可 |
| `llm_adapter_path` | 留空 | 多数训练用不到 |

**常见踩坑**：只填了主模型，忘了 VAE 或 Qwen3；或者想「顺便训一下文本编码器」，把上面两个「只训…」选项都打开了——这样配置是冲突的。

---

## 2. 数据集、分辨率与标签

### 数据放哪里

| 参数 | 说明 |
|------|------|
| `train_data_dir` | 训练图片文件夹（子文件夹可对应不同角色或概念） |
| `reg_data_dir` | 正则化图片；**大多数情况留空** |
| `prior_loss_weight` | 只有用了正则集才需要关心 |

文件夹结构和 Kohya 类似：**每个子文件夹里放图，旁边放同名标签文件**。

### 分辨率与分桶

| 参数 | 默认 | 建议 |
|------|------|------|
| `resolution` | `1024,1024` | 人物、通用 LoRA 优先 1024；**别习惯性填 512** |
| `enable_bucket` | 开启 | 横图竖图混在一起时建议开着 |
| `min_bucket_reso` / `max_bucket_reso` | 256 / 2048 | 图都不大时，可以把上限调低一点 |
| `bucket_reso_steps` | 64 | 一般不用改 |

分辨率越高越吃显存；分桶范围设得不合适，可能导致图片被放大太多或算力浪费。

### 标签：从 `.txt` 到 JSON

| 参数 | 说明 |
|------|------|
| `prefer_json_caption` | **建议开启**，优先读同名 `.json` 标签 |
| `caption_extension` | 没有 JSON 时，回退读 `.txt` |
| `shuffle_caption` | 训练时打乱标签顺序；JSON 标签解析后使用相同规则 |
| `keep_tokens` | 打乱时保留前几个词不动（触发词建议放前面） |

JSON 标签按以下固定字段顺序展开（表单里也有提示）：

```text
quality / count / character / series / artist / appearance[] / tags[] / environment[] / nl
```

例如 `image1.png` 对应 `image1.json`：

```json
{
  "quality": "masterpiece",
  "count": 1,
  "character": "character name",
  "appearance": ["blue eyes", "red dress"],
  "tags": ["smile"],
  "environment": ["indoors"],
  "nl": "a natural language description"
}
```

字段可写字符串、数字或对应数组，空值会跳过。JSON 没有可用内容时回退读取文本标签；JSON 语法错误或字段类型不受支持时会明确报错，不会静默按无标签训练。

你以前用「一行逗号 tag」完全可以继续用；如果愿意，把角色名、外观、环境分开写进 JSON，Anima 往往吃得更好。触发词放在 `character` 或 `tags` 前面，并配合 `keep_tokens`，效果更稳。

**注意**：如果开了「缓存文本编码器输出」（`cache_text_encoder_outputs`），需要**关掉** `shuffle_caption`，否则两者会打架。

---

## 3. 训多久、一批几张

| 参数 | 说明 |
|------|------|
| `max_train_epochs` | 训练轮数；图少时不要设太大 |
| `train_batch_size` | 每批几张图；越大越快，也越吃显存 |
| `gradient_accumulation_steps` | 相当于加大 batch，但不额外占显存 |

经验上，在分辨率和数据量差不多时，**累计一千到三千步**往往就能看出角色轮廓；具体还要看维度、学习率和素材质量。

总步数估算方式和 SDXL 一样：**每轮 batch 数 × 训练轮数**。

---

## 4. LoRA 维度与适配器类型

### 标准 LoRA（默认，建议先用这个）

| 参数 | 默认 | 说明 |
|------|------|------|
| `network_dim` | 16 | LoRA 容量；4–128 都常见，**不是越大越好** |
| `network_alpha` | 16 | 常和 dim 相同，或设为 dim 的一半 |
| `network_dropout` | 0 | 图很少时可以略加一点；默认 0 就行 |
| `network_weights` | 空 | 从已有 LoRA 接着训时填路径 |

从 SDXL 过来，`dim=16、alpha=16` 仍是稳妥起点。图少可以试 8–16；如果过拟合，先减轮数或略加 dropout，别一上来就把 dim 拉满。

### 其他类型（了解即可）

| 类型 | 适合什么时候试 |
|------|----------------|
| **LoKr** | 想要更强表达、愿意多调参；详见 [训练指南 · LoKr](./anima-training.md#进阶lokr-训练参数参考) |
| **T-LoRA** | 数据少、怕过拟合；收敛会慢一些，详见 [训练指南 · T-LoRA](./anima-training.md#进阶t-lora-训练教程) |

日常训人物或画风，**先用标准 LoRA 跑通**，满意了再考虑换 LoKr 或 T-LoRA。

---

## 5. 学习率与优化器

| 参数 | 你需要知道的 |
|------|--------------|
| `learning_rate` | 如果单独填了 `unet_lr` 或 `text_encoder_lr`，这一项会被忽略 |
| `unet_lr` | 只训主网络时，**主要靠它**；常见从 `1e-4` 试起 |
| `text_encoder_lr` | 只有训文本编码器时才用；默认 `1e-5` |
| `optimizer_type` | **AdamW8bit** 省心；**Automagic** 学习率通常要小很多（约 `1e-6`），不能当普通 AdamW 用 |
| `lr_scheduler` | `cosine`、`constant` 都常见，和 SDXL 差不多 |

用 **Automagic** 或 **CAME** 时如果 loss 变成 NaN，先确认 PyTorch 版本 ≥ 2.5，**不要**靠开 `full_fp16` / `full_bf16` 硬撑。更多排错见 [训练指南 · 常见问题](./anima-training.md#常见问题)。

**Prodigy** 在 SDXL 上很常用，Anima 也能用；建议先用小数据集试一轮，确认能收敛再加轮数。

---

## 6. Anima 专有选项（建议先别动）

下面这些在 SDXL 里没有对应项，**保持默认**通常最省心；乱改可能出现「能跑完，但效果怪」的情况。

| 参数 | 默认 | 建议 |
|------|------|------|
| `timestep_sampling` | `shift` | **保持默认** |
| `discrete_flow_shift` | `3.0` | 保持默认即可 |
| `weighting_scheme` | `uniform` | 一般不用改 |
| `attn_mode` | 留空（自动） | 留空最省事；没有 flash 时可选手动选 `sdpa` |
| `split_attn` | 关闭 | 只有显存非常紧时才开，会变慢 |

把模型、数据、维度、学习率先调顺，再考虑在这里做实验。

---

## 7. 精度、缓存与显存

| 参数 | 作用 | 建议 |
|------|------|------|
| `mixed_precision` | 训练用半精度 | 显卡支持的话用 **bf16** |
| `gradient_checkpointing` | 用多一点计算换显存 | 建议**开着** |
| `cache_latents` | 缓存图片编码结果 | 多轮训练时开着能省时间、省显存 |
| `cache_latents_to_disk` | 缓存写到硬盘 | 硬盘空间够可以开 |
| `cache_text_encoder_outputs` | 缓存提示词编码结果 | 显存紧时有用；**须关掉 shuffle_caption** |
| `cache_text_encoder_outputs_to_disk` | 文本缓存写到硬盘 | 大项目常用 |
| `full_fp16` / `full_bf16` | 可训练部分全用半精度 | Anima **一般不推荐** |
| `fp8_base` | 底座用 FP8 省显存 | 实验项；先标准精度跑通再说 |
| `max_data_loader_n_workers` | 加载数据的进程数 | Windows 建议保持 **0** |

你在 SDXL 上习惯开的 latent 缓存、文本编码器缓存，在 Anima 里同样好用；记得**文本缓存和打乱标签不能同时开**。

---

## 8. 训练预览图

开启 `enable_preview` 后，训练过程中会定期出预览图。**预览用的 CFG、步数和最终推理不一定相同**，只是帮你看训练进度。

| 参数 | Anima 建议 | SDXL 里你可能习惯 |
|------|------------|-------------------|
| `sample_cfg` | **4–5** | 7 左右 |
| `sample_steps` | **30–50** | 20–28 |
| `sample_width` / `sample_height` | 1024 | 512 或 1024 |
| `positive_prompts` / `negative_prompts` | 默认偏保守的人物预览 | 建议写上你的触发词 |

预览会多占一些显存和时间；显存紧可以先关掉，用 Tensorboard 看 loss 曲线。

---

## 9. 一套稳妥的起步参数

在 **Anima LoRA 标准模式** 下，可以先按下面填一版，再按自己的数据和显卡微调：

```text
lora_type = lora
resolution = 1024,1024
enable_bucket = true
network_dim = 16
network_alpha = 16
network_train_unet_only = true
optimizer_type = AdamW8bit
unet_lr = 1e-4
max_train_epochs = 10        # 按你的图多少调整
mixed_precision = bf16
gradient_checkpointing = true
prefer_json_caption = true   # 准备好 JSON 标签
timestep_sampling = shift
discrete_flow_shift = 3.0
attn_mode = （留空）
```

想用命令行的话，可以参考 [`docs/examples/anima-lora-benchmark-kohya.toml`](./examples/anima-lora-benchmark-kohya.toml)，里面的注释和页面对得上。

---

## 10. 刚开始建议先别改这些

- Anima 专有的时间步、权重分布等 Flow 相关参数（除非你已读过官方说明）
- `full_fp16` / `full_bf16`
- 同时开启「只训主网络」和「只训文本编码器」
- 一上来就用 **LoKr + 全矩阵 + 很高的学习率**
- 把 SDXL 的 `clip_skip`、V-pred、旧采样器名字原样抄过来

---

## 还想深入了解

- [Anima LoRA 训练指南](./anima-training.md) — 下载模型、命令行训练、LoKr / T-LoRA 进阶
- [Anima LoRA 预设](./anima-lora-presets.md) — 可导入的起点配置
- [Flash Attention 安装](./flash-attention.md) — 想加速 Attention 时可选
- [训练参数说明（通用）](/lora/params.html) — SD / SDXL 通用项；Anima 专用以本文为准

---

如果页面上的名称和本文略有出入，以 **Anima LoRA → 标准模式** 里的表单为准。

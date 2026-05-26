# Anima Edit 双参考图 Conditioning（方案 2）设计草案

> **状态**：P0 训练与 WebUI（`anima-edit-lora` + manifest 预览）已实现；推理多参考仍 defer  
> **分支**：`anima-edit`  
> **关联**：单参考图能力见 [docs/anima-training.md](../anima-training.md#图像编辑--条件训练实验)

## 1. 目标与非目标

### 1.1 目标（P0）

在现有 **Anima conditioning LoRA** 链路上，扩展为 **1 张目标图 + 2 张参考图** 的训练协议（截图中的 **方案 2：拼接多个 reference latent**），不引入新的多图融合模块。

训练时输入序列：

```text
noisy target latent  +  ref1 latent  +  ref2 latent  →  预测 target
```

对应引擎侧即为沿 DiT 输入的 **时间维 `dim=2`** 拼接（与当前单参考一致，仅 `T` 从 `2` 变为 `3`）。

### 1.2 非目标（P0 不做）

| 项 | 说明 |
|----|------|
| 推理 / ComfyUI 多参考 | 训练跑通、loss 与训练预览可观测即可；`--cn` 多图、ComfyUI-Cosmos-Reference 多参考 **本阶段不做** |
| 3 张及以上参考图 | P0 固定 **N=2**；后续再评估是否开放 N=4 + padding |
| 方案 3（独立多图条件模块） | 不采用 ControlNet/IP-Adapter 式新分支 |
| 方案 1（拼贴成单图） | 仅作对照实验，不纳入 P0 实现 |
| ImagePulse 全量训练 | 仅作后续验证数据集；P0 冒烟以本机小集为主 |

## 2. 背景与可行性假设

### 2.1 与 Mirumo 原版的关系

Mirumo / 上游 **未声明** 仅按「1 噪声 + 1 参考」调优过多参考序列；本能力属于 **协议扩展 + 冒烟验证**，不保证与单参考同等稳定。

**验收标准（冒烟）**：512 分辨率、`gradient_checkpointing=true`、极小数据集上：

- 训练可启动、可完成若干 step / 1～2 epoch
- 无 shape / device / cache 相关硬错误
- 训练预览（若开启）可生成图像（质量不作硬性要求）

### 2.2 显存与分辨率

| 项 | P0 约定 |
|----|---------|
| 冒烟分辨率 | **512×512**（降低 VRAM，便于验证 `T=3`） |
| 梯度检查点 | **开启** `gradient_checkpointing` |
| 批量 | `train_batch_size=1` |
| 缓存 | 保持 `cache_latents=true`、`cache_text_encoder_outputs=true`（与单参考 Anima Edit 一致） |

正式 1024 训练留到冒烟通过后再开。

## 3. 数据协议：子目录模式（双参考）

### 3.1 目录布局

与单参考「两个平级目录 + 同名文件」不同，双参考采用 **按目标样本分子目录**，参考图文件名在各自子目录内可重复（如都叫 `1.png` / `2.png`），**允许同名文件**。

```text
dataset_root/
├── target/
│   ├── sampleA.png
│   ├── sampleA.txt          # 标签仅放在 target 侧
│   └── sampleB.png
│   └── sampleB.txt
└── reference/
    ├── sampleA/               # 子目录名 = target 主文件名（无扩展名）
    │   ├── 1.png              # 参考图 1（排序见下）
    │   └── 2.png              # 参考图 2
    └── sampleB/
        ├── 1.png
        └── 2.png
```

**配对规则**：

1. `target/` 下每张训练图 `target/<stem>.<ext>` 对应 `reference/<stem>/` 目录。
2. `reference/<stem>/` 内取 **恰好 2 张** 图片（P0）；不足 2 张或超过 2 张 → **启动前报错**（不静默截断）。
3. 子目录内图片按 **文件名排序** 后取前 2 张，保证 ref1/ref2 顺序可复现。
4. 参考图与目标图 **宽高必须一致**（与单参考相同；bucket 下按 target 桶处理，参考图做相同 crop/resize）。

### 3.2 与单参考模式兼容

| 模式 | `conditioning_data_dir` 含义 | 检测方式 |
|------|------------------------------|----------|
| 单参考（现有） | 平级目录，与 target **同名文件** 一一对应 | 目录下直接是图片文件，无「仅含子目录」的样本级结构 |
| 双参考（P0 新增） | 父目录；其下 **子目录名 = target stem** | UI 开关 `multi_reference_mode=true` 且 `reference_count=2` |

实现时：**由 WebUI 写入的 `dataset_config.toml` 区分**，引擎 `train_util` 根据 subset 元数据或目录探测选择加载器。

### 3.3 `dataset_config.toml` 草案（生成目标）

```toml
[general]
caption_extension = ".txt"

[[datasets]]
resolution = [512, 512]
batch_size = 1
enable_bucket = true

[[datasets.subsets]]
image_dir = "./data/edit3/target"
conditioning_data_dir = "./data/edit3/reference"
conditioning_multi_reference = true
conditioning_reference_count = 2
```

> `conditioning_multi_reference` / `conditioning_reference_count` 为 **拟新增字段**（名称实现时可微调，文档先固定语义）。

## 4. 引擎改动（`vendor/sd-scripts`）

### 4.1 数据加载

| 位置 | 改动要点 |
|------|----------|
| `library/train_util.py` `ImageInfo` | `cond_img_path: str` → 增加 `cond_img_paths: list[str]`（长度 2） |
| `ControlNetDataset` 初始化 | 单参考：保持 `glob(basename)`；双参考：扫描 `reference/<stem>/`，排序后取 2 路径 |
| `__getitem__` | 对每张参考图走现有 cond 变换 / latent 读取；**沿 `dim=2` stack** 为 `[C, 2, H, W]` 再进入 batch |
| `cache_latents` | 每个 `cond_img_paths[i]` 独立 `cond_latents_npz`（或等价命名），加载时按序 stack |

### 4.2 训练步

`anima_train_network.py` 现有逻辑：

```python
noisy_model_input = torch.cat([noisy_model_input, conditioning_latents], dim=2)
```

P0 要求：`conditioning_latents` 形状为 `[B, C, 2, H, W]` 时直接与 `[B, C, 1, H, W]` 噪声拼接 → `[B, C, 3, H, W]`；`model_pred` 仍只取 `[:, :, :1, ...]`。

需确认：`conditioning_latents.ndim == 5` 且 `shape[2]==2` 时 **不再** 错误 `unsqueeze(2)`。

### 4.3 采样预览（训练内）

P0 **可保留单 `--cn`** 仅用于「是否出图」冒烟；**不要求** 双 `--cn`。若实现成本低，可预留 `controlnet_images: list` 但 UI 不暴露。

## 5. WebUI 改动（P0）

### 5.1 Schema（`mikazuki/schema/sd3-lora.ts`）

在「图像编辑（实验功能）」下增加：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `multi_reference_mode` | boolean | false | 开启双参考子目录协议 |
| `conditioning_reference_count` | number | 2 | P0 固定为 2，UI 只读或隐藏 |

单参考时：仍显示现有 `target_data_dir` + `conditioning_data_dir`（平级同名）。

双参考时：

- `target_data_dir`：指向 `target/`
- `conditioning_data_dir`：指向 `reference/`（父目录）
- 说明文案：每个 target 样本需在 `reference/<文件名无扩展名>/` 下放置 **2 张** 参考图，文件名可均为 `1.png`、`2.png` 等，按排序取前 2 张。

**预览（P0）**：可暂时禁用双参考下的「图像编辑预览」，或仍用单张 `sample_conditioning_image` 仅作占位；不以双 `--cn` 为验收项。

### 5.2 后端（`mikazuki/app/api.py`）

- `_prepare_conditioning_dataset_config`：当 `multi_reference_mode` 时写入 §3.3 字段。
- 校验：`reference/<stem>/` 是否存在且含 2 张图。
- `apply_anima_training_defaults`：双参考冒烟建议默认 `resolution=512`（可选，或由用户手填）。

### 5.3 Adapter（`mikazuki/anima_backend/adapter.py`）

- `UI_ONLY_FIELDS` 增加 `multi_reference_mode`、`conditioning_reference_count`。

## 6. 冒烟测试计划

### 6.1 本机数据集 `data/edit3`

用户指定路径：`D:\ai\lora-scripts-next\data\edit3`（三张图级别小集）。

**建议整理为**（若尚未按子目录放置，实现前人工整理一次）：

```text
data/edit3/
├── target/
│   └── <one_sample>.png + .txt
└── reference/
    └── <one_sample>/
        ├── 1.png    # 参考 1
        └── 2.png    # 参考 2
```

若当前仅为 3 张平铺图，需在 P0 开发时对照该目录实际结构适配或补一层导入脚本（实现阶段处理）。

### 6.2 冒烟配置要点

```toml
resolution = "512,512"
train_batch_size = 1
gradient_checkpointing = true
conditioning = true
cache_latents = true
cache_text_encoder_outputs = true
sample_at_first = false
max_train_epochs = 2   # 冒烟
network_dim = 8        # 可选，进一步降过拟合风险
unet_lr = 3e-5
```

### 6.3 通过 / 失败判定

| 结果 | 条件 |
|------|------|
| 通过 | 生成 `dataset_config` 正确；训练 ≥ N step；日志出现 conditioning latent cache；无崩溃 |
| 失败 | shape 不匹配；仅加载 1 张参考；reference 子目录未配对；OOM（512 + ckpt 仍 OOM 则记录并再降参） |

## 7. ImagePulseV2 子集（后续）

- 数据集：[ImagePulseV2-Edit-Merge](https://modelscope.cn/datasets/DiffSynth-Studio/ImagePulseV2-Edit-Merge)（图1 + 图2 → 合并图）。
- 下载脚本：`script/ops/fetch_imagepulsev2_sample.py`（后台任务，与 P0 实现可并行）。
- 落地到 `data/imagepulsev2-edit-merge-100/` 后，再写转换脚本：每条样本 → §3.1 目录结构。

## 8. 实现顺序（草案 → 代码）

1. **本文档评审**（当前步骤）
2. `train_util` + `config_util`：双参考加载与 TOML 字段
3. `anima_train_network`：确认 `T=3` 拼接
4. `mikazuki` API + schema + 前端 dist 文案
5. `data/edit3` 整理 + 512 冒烟
6. ImagePulse 转换与对比（可选）

## 9. 风险备忘

| 风险 | 缓解 |
|------|------|
| `T=3` 未在基座充分验证 | 仅冒烟；对比单参考同数据 |
| 参考顺序敏感 | 文档约定排序；ImagePulse 固定 ref1/ref2 语义 |
| 与单参考配置混用 | UI 模式开关 + TOML 显式字段 |
| 预览/推理未同步 | P0 明确不做；避免用户误以为已支持双参考推理 |

## 10. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-27 | 初稿：P0 双参考、子目录协议、512 冒烟、不做推理 |

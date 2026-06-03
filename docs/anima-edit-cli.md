# Anima Edit 命令行训练

> **分支**：`git checkout anima-edit`  
> **入口脚本**：[`scripts/dev/anima_train_network.py`](../scripts/dev/anima_train_network.py)（适配本仓库 TOML 后委托 `vendor/sd-scripts`）  
> **WebUI 用户**：见 [README-zh](../README-zh.md)；本文面向习惯 `accelerate launch` 的进阶用户。

---

## 1. 通用启动方式

在仓库根目录执行（Windows PowerShell 用 `` ` `` 续行，或写成一行）：

```powershell
accelerate launch --num_cpu_threads_per_process 1 `
  scripts/dev/anima_train_network.py `
  --config_file docs/examples/<你的训练配置>.toml
```

等价写法：

```powershell
python -m accelerate.commands.launch --num_cpu_threads_per_process 1 `
  scripts/dev/anima_train_network.py --config_file docs/examples/<你的训练配置>.toml
```

训练配置 TOML 中通常包含：

| 字段 | 含义 |
|------|------|
| `pretrained_model_name_or_path` | Anima DiT 主权重 |
| `vae` / `qwen3` | VAE、Qwen3（路径按本机 `sd-models/` 填写） |
| `dataset_config` | 指向 **数据集 TOML**（见下文） |
| `conditioning = true` | 开启图像编辑 / 条件训练 |
| `network_module = "networks.lora_anima"` | Edit LoRA |
| `cache_latents = true` | 编辑训练建议开启 |
| `cache_text_encoder_outputs = true` | 建议开启 |
| `sample_at_first = false` | 避免 step 0 噪声预览误导 |

冒烟（不跑满训练，仅验证能启动）：

```powershell
$env:ANIMA_BACKEND_WRAPPER_SMOKE = "1"
python scripts/dev/anima_train_network.py --config_file docs/examples/anima-edit-dual-ref-smoke.toml
```

---

## 2. 单张参考图（CLI）

### 2.1 目录布局

```text
my_dataset/
├── target/
│   ├── foo.png
│   └── foo.txt
└── reference/
    └── foo.png          # 与 target 同名；尺寸一致
```

### 2.2 数据集 TOML

单参考 **不要** 写 `conditioning_multi_reference`（或设为 `false`）。示例：[anima-edit-single-ref-dataset.toml](examples/anima-edit-single-ref-dataset.toml)：

```toml
[[datasets.subsets]]
image_dir = "./data/my_dataset/target"
conditioning_data_dir = "./data/my_dataset/reference"
```

### 2.3 训练与预览

| 用途 | 配置文件 |
|------|----------|
| 12 epoch 示例 | [anima-edit-single-ref-12epoch.toml](examples/anima-edit-single-ref-12epoch.toml) |
| 预览 manifest | [anima-edit-single-ref-sample-prompts.toml](examples/anima-edit-single-ref-sample-prompts.toml) |

```powershell
accelerate launch --num_cpu_threads_per_process 1 `
  scripts/dev/anima_train_network.py `
  --config_file docs/examples/anima-edit-single-ref-12epoch.toml
```

---

## 3. 双张参考图 / 多图编辑（CLI）★

P0 固定为 **每个样本 2 张参考图**（latent 时间维拼接，`T=3`：noisy target + ref1 + ref2）。

### 3.1 目录布局

```text
my_dataset/
├── target/
│   ├── foo.png
│   └── foo.txt
└── reference/
    └── foo/             # 文件夹名 = target 文件名（无扩展名）
        ├── 1.png        # 按文件名排序，取前 2 张
        └── 2.png
```

### 3.2 数据集 TOML（关键字段）

示例：[anima-edit-dual-ref-dataset.toml](examples/anima-edit-dual-ref-dataset.toml)：

```toml
[[datasets.subsets]]
image_dir = "./data/my_dataset/target"
conditioning_data_dir = "./data/my_dataset/reference"
conditioning_multi_reference = true
conditioning_reference_count = 2
```

| 字段 | 必须 | 说明 |
|------|------|------|
| `conditioning_multi_reference` | 是 | `true` 启用双参考加载 |
| `conditioning_reference_count` | 是 | P0 固定为 `2` |
| `conditioning_data_dir` | 是 | `reference/` 根目录 |
| `image_dir` | 是 | `target/` 目录 |

训练 TOML 中设置 `dataset_config = "./path/to/dataset.toml"` 且 **`conditioning = true`**。

### 3.3 训练命令

| 用途 | 配置 | 命令 |
|------|------|------|
| 冒烟 2 step | [anima-edit-dual-ref-smoke.toml](examples/anima-edit-dual-ref-smoke.toml) | 见文件头注释 |
| 10 epoch | [anima-edit-dual-ref-10epoch.toml](examples/anima-edit-dual-ref-10epoch.toml) | 同上 |
| 768 / 1024 数据集 | [anima-edit-dual-ref-dataset-768.toml](examples/anima-edit-dual-ref-dataset-768.toml) 等 | 改 `image_dir` 路径 |

```powershell
accelerate launch --num_cpu_threads_per_process 1 `
  scripts/dev/anima_train_network.py `
  --config_file docs/examples/anima-edit-dual-ref-10epoch.toml
```

### 3.4 双参考训练预览（manifest）

不再使用旧版 `sample_prompts.txt` 里的 `--cn` 单路径；请用 **`sample-prompts.toml`**，每条样本用 `reference_dir` + `reference_count = 2`：

```toml
[[prompts]]
prompt = "your full training caption from target/foo.txt"
negative_prompt = "low quality, blurry"
width = 512
height = 512
scale = 4.5
seed = 42
sample_steps = 40
reference_dir = "./data/my_dataset/reference/foo"
reference_count = 2
```

示例文件：

- [anima-edit-sample-prompts.toml](examples/anima-edit-sample-prompts.toml)（edit3）
- [anima-edit-dual-ref-multi-preview.toml](examples/anima-edit-dual-ref-multi-preview.toml)（多条 `[[prompts]]`）
- [anima-edit-imagepulse-sample-prompts.toml](examples/anima-edit-imagepulse-sample-prompts.toml)（ImagePulse 数据）

生成 manifest：

```powershell
python script/ops/generate_anima_edit_sample_prompts.py `
  --data-dir data/my_dataset `
  --out docs/examples/my-dual-ref-preview.toml
```

### 3.5 一键拉取双参考小数据集

```powershell
python script/ops/fetch_multiref_anima_edit_subset.py --count 48 --seed 42
```

输出 `data/anima-edit-multiref-48/`（target + `reference/<stem>/` 双图）。将 [anima-edit-dual-ref-dataset.toml](examples/anima-edit-dual-ref-dataset.toml) 里的 `image_dir` / `conditioning_data_dir` 改为该路径即可开训。

---

## 4. 示例配置索引

| 场景 | 数据集 TOML | 训练 TOML |
|------|-------------|-----------|
| 单参考 12 epoch | [single-ref-dataset](examples/anima-edit-single-ref-dataset.toml) | [single-ref-12epoch](examples/anima-edit-single-ref-12epoch.toml) |
| 双参考冒烟 | [dual-ref-dataset](examples/anima-edit-dual-ref-dataset.toml) | [dual-ref-smoke](examples/anima-edit-dual-ref-smoke.toml) |
| 双参考 10 epoch | 同上 | [dual-ref-10epoch](examples/anima-edit-dual-ref-10epoch.toml) |
| 双参考多图预览 | 同上 | [dual-ref-multi-preview](examples/anima-edit-dual-ref-multi-preview.toml) |
| ImagePulse 双参考 | [imagepulse-dataset](examples/anima-edit-imagepulse-dataset.toml) | [imagepulse-10epoch](examples/anima-edit-imagepulse-10epoch.toml) |

上游直连（不经 wrapper 适配时，仅当你明确需要）：`vendor/sd-scripts/anima_train_network.py`，配置见 `*-sd-scripts.toml` 同名示例。

---

## 5. 相关文档

- [anima-training.md — 图像编辑](anima-training.md#图像编辑--条件训练实验)（WebUI + 数据集选型）
- [anima-edit-multi-reference.md](design/anima-edit-multi-reference.md)（双参考设计）
- [anima-edit-vram-resolution.md](design/anima-edit-vram-resolution.md)（显存与分辨率）
- [anima-backend.md](anima-backend.md)（wrapper / 上游 pin）

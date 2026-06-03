# Anima Edit 示例总览

> **分支**：`anima-edit`  
> **WebUI**：[/lora/anima-edit.html](http://127.0.0.1:28000/lora/anima-edit.html)  
> **命令行**：[anima-edit-cli.md](anima-edit-cli.md)  
> **设计说明**：[anima-edit-multi-reference.md](design/anima-edit-multi-reference.md)

**路径约定**：下文与 `docs/examples/*.toml` 中的数据集路径均为 **相对仓库根目录** 的占位（如 `./data/edit3/`）。`data/` 目录默认 **不提交 Git**；克隆后请自备数据，或运行 [§六](#六辅助脚本) 中的拉取/构建脚本，再按需改 TOML 中的 `image_dir` / `conditioning_data_dir`。

本文汇总 **单图参考** 与 **双图参考（多图编辑）** 的数据布局、训练配置、预览 manifest 与文档例图，便于按场景选用。

---

## 一、先选对模式

| 模式 | 每个样本 | 参考目录布局 | 数据集关键字段 |
|------|----------|--------------|----------------|
| **单图编辑** | 1 张参考 + 1 张目标 | `reference/<stem>.png` 与 `target/<stem>.png` **同名** | 不写 `conditioning_multi_reference` |
| **多图编辑（双参考）** | 2 张参考 + 1 张目标 | `reference/<stem>/` 下放 2 张图（按文件名排序取前 2 张） | `conditioning_multi_reference = true`<br>`conditioning_reference_count = 2` |

```text
单图                          双图（多参考）
my_dataset/                   my_dataset/
├── target/                   ├── target/
│   ├── foo.png               │   ├── foo.png
│   └── foo.txt               │   └── foo.txt
└── reference/                └── reference/
    └── foo.png                   └── foo/
                                      ├── 1.png
                                      └── 2.png
```

标签（`.txt` / `.json`）放在 **`target/`**，参考图与目标图 **尺寸须一致**。

---

## 二、我想… 快速选型

| 我想… | 数据集 | 训练配置 | 预览 manifest |
|-------|--------|----------|---------------|
| WebUI 试跑双参考 | 自备或 [edit3](#本机小集-edit3) | 在 Edit 页选「双张参考图」 | 表单自动生成或手写 `prompt_file` |
| CLI 双参考冒烟（2 step） | [dual-ref-dataset.toml](examples/anima-edit-dual-ref-dataset.toml) | [dual-ref-smoke.toml](examples/anima-edit-dual-ref-smoke.toml) | — |
| CLI 双参考正式 10 epoch | 同上（或 [768](examples/anima-edit-dual-ref-dataset-768.toml) / [1024](examples/anima-edit-dual-ref-dataset-1024.toml)） | [dual-ref-10epoch.toml](examples/anima-edit-dual-ref-10epoch.toml) | [sample-prompts.toml](examples/anima-edit-sample-prompts.toml) |
| CLI 双参考多条预览 | 同上 | [dual-ref-multi-preview.toml](examples/anima-edit-dual-ref-multi-preview.toml) | 文件内多条 `[[prompts]]` |
| CLI 单参考 12 epoch | [single-ref-dataset.toml](examples/anima-edit-single-ref-dataset.toml) | [single-ref-12epoch.toml](examples/anima-edit-single-ref-12epoch.toml) | [single-ref-sample-prompts.toml](examples/anima-edit-single-ref-sample-prompts.toml) |
| 拉公开双参考小集（48 对） | 运行 [fetch 脚本](#辅助脚本) → `data/anima-edit-multiref-48/` | 改 dual-ref-dataset 路径 | `generate_anima_edit_sample_prompts.py` |
| 文档门面 / README 用图 | [showcase 工作流](design/anima-edit-showcase-workflow.md) | sample-only 配置 | 见 [§五](#五文档例图与-showcase) |

---

## 三、单图编辑（单张参考）

### 3.1 配置文件

| 用途 | 文件 |
|------|------|
| 数据集 | [anima-edit-single-ref-dataset.toml](examples/anima-edit-single-ref-dataset.toml) |
| 训练 12 epoch | [anima-edit-single-ref-12epoch.toml](examples/anima-edit-single-ref-12epoch.toml) |
| 预览 manifest | [anima-edit-single-ref-sample-prompts.toml](examples/anima-edit-single-ref-sample-prompts.toml) |
| 仅推理（已有权重） | [anima-edit-single-ref-sample-only.toml](examples/anima-edit-single-ref-sample-only.toml) |
| 上游直连变体 | [anima-edit-single-ref-12epoch-sd-scripts.toml](examples/anima-edit-single-ref-12epoch-sd-scripts.toml) |

### 3.2 数据与构建

| 路径 / 脚本 | 说明 |
|-------------|------|
| `data/anima-edit-single-showcase/` | 32 对展示集（常由 ImagePulse 双参考集取 `reference/<stem>/1.png` 转单参考） |
| `script/ops/build_anima_edit_single_ref_showcase.py` | 构建上述展示集 |

### 3.3 CLI 一键命令

```powershell
accelerate launch --num_cpu_threads_per_process 1 `
  scripts/dev/anima_train_network.py `
  --config_file docs/examples/anima-edit-single-ref-12epoch.toml
```

---

## 四、多图编辑（双张参考）

### 4.1 配置文件

| 用途 | 文件 |
|------|------|
| 数据集（512） | [anima-edit-dual-ref-dataset.toml](examples/anima-edit-dual-ref-dataset.toml) |
| 数据集 768 / 1024 | […-768.toml](examples/anima-edit-dual-ref-dataset-768.toml) · […-1024.toml](examples/anima-edit-dual-ref-dataset-1024.toml) |
| 冒烟 2 step | [anima-edit-dual-ref-smoke.toml](examples/anima-edit-dual-ref-smoke.toml) |
| 训练 10 epoch | [anima-edit-dual-ref-10epoch.toml](examples/anima-edit-dual-ref-10epoch.toml) |
| 多组预览 | [anima-edit-dual-ref-multi-preview.toml](examples/anima-edit-dual-ref-multi-preview.toml) |
| 通用 preview 示例 | [anima-edit-sample-prompts.toml](examples/anima-edit-sample-prompts.toml) · [multi](examples/anima-edit-sample-prompts-multi.toml) |
| 上游直连变体 | `*-sd-scripts.toml` 同名文件 |

**数据集 TOML 核心片段：**

```toml
[[datasets.subsets]]
image_dir = "./data/my_dataset/target"
conditioning_data_dir = "./data/my_dataset/reference"
conditioning_multi_reference = true
conditioning_reference_count = 2
```

**预览 manifest 核心片段：**

```toml
[[prompts]]
prompt = "与 target/foo.txt 一致的完整 caption"
reference_dir = "./data/my_dataset/reference/foo"
reference_count = 2
width = 512
height = 512
```

### 4.2 开发用小集 edit3（可选）

示例 TOML 默认指向 **`./data/edit3/`**（VRAM bench 与双参考冒烟常用；**需本地自备**，不在 Git 中）。典型结构含 `reference/sample1/1.png` + `2.png`。  
默认见 [dual-ref-dataset.toml](examples/anima-edit-dual-ref-dataset.toml) 的 `image_dir` / `conditioning_data_dir`；换成你自己的目录时只改这两处即可。

### 4.3 CLI 一键命令

```powershell
# 冒烟
accelerate launch --num_cpu_threads_per_process 1 `
  scripts/dev/anima_train_network.py `
  --config_file docs/examples/anima-edit-dual-ref-smoke.toml

# 10 epoch
accelerate launch --num_cpu_threads_per_process 1 `
  scripts/dev/anima_train_network.py `
  --config_file docs/examples/anima-edit-dual-ref-10epoch.toml
```

---

## 五、文档例图与 Showcase

训练用数据与 **README / 文档门面图** 分离，流程见 [anima-edit-showcase-workflow.md](design/anima-edit-showcase-workflow.md)。

### 5.1 单参考门面

| 类型 | 路径 |
|------|------|
| 精选案例（推荐对外） | `docs/assets/anima-edit-showcase-curated/` · `data/anima-edit-showcase-curated/` |
| Hero 管线验证图 | `docs/assets/anima-edit-single-ref/`（ImagePulse 前几条，**不宜当官方门面**） |
| 登记案例 | `script/ops/register_anima_edit_showcase_case.py` |
| 生成 preview TOML | `script/ops/generate_anima_edit_showcase_prompts.py` |
| sample-only 推理 | [anima-edit-showcase-sample-only.toml](examples/anima-edit-showcase-sample-only.toml) |

### 5.2 双参考门面

| 类型 | 路径 |
|------|------|
| 精选双参考案例 | `docs/assets/anima-edit-showcase-dual-curated/` |
| 数据集 | [anima-edit-showcase-dual-dataset.toml](examples/anima-edit-showcase-dual-dataset.toml) |
| 预览 manifest | [anima-edit-showcase-dual-sample-prompts.toml](examples/anima-edit-showcase-dual-sample-prompts.toml) |
| sample-only | [anima-edit-showcase-dual-sample-only.toml](examples/anima-edit-showcase-dual-sample-only.toml) |
| 生成脚本 | `script/ops/generate_anima_edit_showcase_dual_prompts.py` |

---

## 六、辅助脚本

| 脚本 | 作用 |
|------|------|
| [fetch_multiref_anima_edit_subset.py](../script/ops/fetch_multiref_anima_edit_subset.py) | 从 MultiRef-benchmark 拉取双参考子集 → `data/anima-edit-multiref-48/` |
| [generate_anima_edit_sample_prompts.py](../script/ops/generate_anima_edit_sample_prompts.py) | 由数据集目录生成 `sample-prompts.toml` |
| [build_anima_edit_single_ref_showcase.py](../script/ops/build_anima_edit_single_ref_showcase.py) | 构建 32 对单参考展示集 |
| [bench_anima_edit_vram.py](../script/ops/bench_anima_edit_vram.py) | 显存 benchmark（配合 `anima-edit-vram-bench-*.toml`） |

---

## 七、显存 Benchmark（可选）

单/双参考、512/768/1024 的 2 epoch bench 配置见 `docs/examples/anima-edit-vram-bench-*.toml`，说明见 [anima-edit-vram-resolution.md](design/anima-edit-vram-resolution.md)。

---

## 八、其它示例（同分支）

| 主题 | 说明 |
|------|------|
| [anima-edit-expression-*.toml](examples/) | 表情编辑向实验配置 |
| [anima-edit-reference.toml](examples/anima-edit-reference.toml) | 早期 50 epoch 探针（脱敏参考） |
| [anima-edit-dataset.toml](examples/anima-edit-dataset.toml) | 通用 conditioning 数据集模板 |

---

## 九、分支差异备忘

| 内容 | `anima-edit` 分支 | `main` 分支 |
|------|-------------------|-------------|
| 双参考命名 | **`dual-ref-*`** | 另有 **`multiref-*`** 示例 TOML |
| ImagePulse 双参考训练 | 未纳入当前 `anima-edit` 树 | 有 `anima-edit-imagepulse-*.toml` |
| 训练代码（双参考） | ✅ 有 | ❌ 无 |

若需要 ImagePulse 或 `multiref-*.toml`，可从 `main` cherry-pick 或复制后改 `image_dir` 路径。

---

## 十、相关链接

| 文档 | 用途 |
|------|------|
| [README-zh.md](../README-zh.md) | 分支首页：WebUI + CLI 快速开始 |
| [anima-edit-cli.md](anima-edit-cli.md) | 命令行字段与命令详解 |
| [anima-training.md — 图像编辑](anima-training.md#图像编辑--条件训练实验) | 完整教程、外部数据集选型 |
| [/help/guide.html#anima-edit-dataset](http://127.0.0.1:28000/help/guide.html#anima-edit-dataset) | WebUI 内目录树状示意图 |

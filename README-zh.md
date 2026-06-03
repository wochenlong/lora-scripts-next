<p align="center">
  <img src="assets/readme/next-trainer-cover.png" alt="Next Trainer" width="880" />
</p>

<h1 align="center">Anima Edit — 图像编辑 LoRA 训练</h1>

<p align="center">
  <b><code>anima-edit</code> 实验分支</b>：在 Next Trainer WebUI 中训练 <strong>Target + Reference</strong> 成对数据，支持<strong>单张</strong>与<strong>双张</strong>参考图编辑 LoRA。<br/>
  <sub>基于 kohya-ss/sd-scripts Anima 与 <a href="https://github.com/Mirumo0u0/sd-scripts">Mirumo0u0/sd-scripts</a> conditioning 实现。</sub>
</p>

<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next/tree/anima-edit"><img src="https://img.shields.io/badge/branch-anima--edit-a78bfa?style=for-the-badge" alt="anima-edit 分支"/></a>
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/anima-edit/README.md"><b>English</b></a>
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/anima-edit/NOTICE.md"><b>致谢</b></a>
</p>

---

## 30 秒开始

```text
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
git checkout anima-edit
run_gui.bat          # Windows；Linux 见下方「安装」
```

| 方式 | 做什么 |
|------|--------|
| **WebUI** | 浏览器 **http://127.0.0.1:28000/lora/anima-edit.html**（侧栏 **「Anima 图像编辑」**） |
| **命令行** | `accelerate launch` + `scripts/dev/anima_train_network.py --config_file …` → **[CLI 完整说明](docs/anima-edit-cli.md)** |

> **整合包 / `main` 分支** 暂无本功能，请用源码 + `anima-edit` 分支。

---

## 命令行训练（进阶）

习惯终端可直接用 **[docs/anima-edit-cli.md](docs/anima-edit-cli.md)**（单张 / 双张参考、数据集 TOML 字段、示例索引）。

**双张参考（多图编辑）最小示例** — 先准备 `target/` + `reference/<stem>/` 两张图，再：

```powershell
# 1) 数据集：conditioning_multi_reference = true，conditioning_reference_count = 2
#    见 docs/examples/anima-edit-dual-ref-dataset.toml

# 2) 冒烟 2 step
accelerate launch --num_cpu_threads_per_process 1 `
  scripts/dev/anima_train_network.py `
  --config_file docs/examples/anima-edit-dual-ref-smoke.toml

# 3) 正式 10 epoch
accelerate launch --num_cpu_threads_per_process 1 `
  scripts/dev/anima_train_network.py `
  --config_file docs/examples/anima-edit-dual-ref-10epoch.toml
```

预览用 `sample-prompts.toml` 的 `reference_dir` + `reference_count = 2`（见 CLI 文档 §3.4）。拉取公开双参考小集：`python script/ops/fetch_multiref_anima_edit_subset.py --count 48 --seed 42`。

---

## 用训练器做图像编辑（WebUI）

### 入口（不要进错页）

| 用途 | 侧栏 / URL |
|------|------------|
| **图像编辑 LoRA（本分支）** | **Anima 图像编辑** → `/lora/anima-edit.html` |
| Anima 文生图 LoRA | **Anima** → `/lora/sd3.html`（与 Edit **无关**） |

训练类型为 **`anima-edit-lora`**。填好 Anima 主模型、VAE、Qwen3、T5 后，在 **「图像编辑数据集与预览」** 中配置 Target / Reference。

### 单张参考图（单图编辑）

**参考图布局** 选 **「单张参考图」**。

```text
my_dataset/
├── target/
│   ├── foo.png
│   └── foo.txt          # 标签放在 target
└── reference/
    └── foo.png          # 与 target 同名；尺寸须一致
```

- 预览：可固定一张参考图，或从目录随机抽取（见表单「图像编辑预览」）。
- 示例配置：[anima-edit-single-ref-12epoch.toml](docs/examples/anima-edit-single-ref-12epoch.toml)

### 双张参考图（多图 / 双参考编辑）

**参考图布局** 选 **「双张参考图」**（P0：每个样本固定 **2** 张参考，沿 latent 时间维拼接）。

```text
my_dataset/
├── target/
│   ├── foo.png
│   └── foo.txt
└── reference/
    └── foo/             # 文件夹名 = target 文件名（无扩展名）
        ├── 1.png        # 按文件名排序取前 2 张
        └── 2.png
```

- 训练监控预览可显示 **参考图1 / 参考图2**（manifest 或自动生成）。
- **CLI**：[anima-edit-cli.md §3](docs/anima-edit-cli.md#3-双张参考图--多图编辑cli)（`conditioning_multi_reference`、`reference_count`、manifest 预览）
- 示例配置：[anima-edit-dual-ref-dataset.toml](docs/examples/anima-edit-dual-ref-dataset.toml)、冒烟 [anima-edit-dual-ref-smoke.toml](docs/examples/anima-edit-dual-ref-smoke.toml)
- 一键拉取小数据集：`python script/ops/fetch_multiref_anima_edit_subset.py --count 48 --seed 42`

**目录示意图（WebUI 内）**：训练页 → **「查看数据集目录示意图 →」** → `/help/guide.html#anima-edit-dataset`（第 ② 页：单张 / 双张树状图）。

### 推荐操作顺序

1. 按上表准备 `target/` + `reference/`（单张或双张布局二选一）。
2. 打开 **`/lora/anima-edit.html`**，填写模型路径与数据集目录。
3. 选择 **单张 / 双张参考图**，开启训练预览；需要多条预览时可填 `prompt_file`（[sample-prompts 示例](docs/examples/anima-edit-sample-prompts-multi.toml)）。
4. 开始训练。WebUI 会自动写 `dataset_config.toml`、启用 latent / TE 缓存，并关闭易误导的 step 0 预览。
5. 用 **训练监控**（`/train-monitor`）看 Loss 与预览是否按参考图变化。

### 训练后推理

LoRA 可在 ComfyUI 配合 [ComfyUI-Cosmos-Reference](https://github.com/Mirumo0u0/ComfyUI-Cosmos-Reference) 使用。P0 **仅保证训练与训练预览**；ComfyUI 多参考推理仍属后续。

### 进一步阅读

| 主题 | 链接 |
|------|------|
| **命令行训练（单/双参考）** | **[docs/anima-edit-cli.md](docs/anima-edit-cli.md)** |
| WebUI 教程、外部数据集 | [docs/anima-training.md — 图像编辑](docs/anima-training.md#图像编辑--条件训练实验) |
| 双参考设计说明 | [docs/design/anima-edit-multi-reference.md](docs/design/anima-edit-multi-reference.md) |
| 显存与分辨率 | [docs/design/anima-edit-vram-resolution.md](docs/design/anima-edit-vram-resolution.md) |

---

## 界面与效果

<p align="center">
  <img src="assets/readme/anima-edit-ui.jpg" alt="Anima Edit 训练页：参考图布局、Target/Reference 路径" width="920" />
</p>

<p align="center"><sub>Anima Edit 专用页：参考图布局（单张/双张）、Target / Reference 目录与预览设置。</sub></p>

<p align="center">
  <img src="assets/readme/anima-edit-sample.jpg" alt="参考图驱动编辑预览示例" width="760" />
</p>

<p align="center"><sub>参考图驱动训练预览示例（示例图由 <b>古柯C17H21NO4</b> 提供）。</sub></p>

### 实验限制（必读）

本分支是 **Anima 文生图基座 + conditioning LoRA**，不是 Qwen Image Edit 等专用编辑大模型。小数据集上后期可能出现固定位置色块/污渍（过拟合），应降学习率、减 epoch 或换更早 checkpoint。

<p align="center">
  <img src="assets/readme/anima-edit-limitations.png" alt="过拟合伪影示例" width="920" />
</p>

---

<details>
<summary><b>安装与环境（Windows / Linux）</b></summary>

```sh
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
git checkout anima-edit

# Windows
run_gui.bat

# Linux
bash install.bash && bash run_gui.sh
```

- 推荐 **Python 3.10**，NVIDIA GPU（RTX 20+），约 7 GB 磁盘（不含模型）。
- 可选 Flash Attention 2：`install_flash_attn.bat` / `install_flash_attn.sh`，见 [docs/flash-attention.md](docs/flash-attention.md)。

</details>

<details>
<summary><b>训练监控</b></summary>

启动训练后打开 **http://127.0.0.1:28000/train-monitor**（勿硬编码 6008 端口）。

<p align="center">
  <img src="assets/readme/screenshot-train-monitor.png" alt="训练监控" width="920" />
  <img src="assets/readme/train-monitor-samples.png" alt="预览与 Loss" width="920" />
</p>

详见 [docs/train-monitor.md](docs/train-monitor.md)。

</details>

<details>
<summary><b>本分支还包含什么 / 不包含什么</b></summary>

| 范围 | 说明 |
|------|------|
| **Anima Edit（单/双参考）** | 本分支主目标 |
| Anima 文生图 LoRA | 继承自主线，在 **Anima** 页，非 Edit 页 |
| SD1.5 / SDXL / Flux | 继承页面，非本分支重点 |
| Release 整合包 | **不含** Anima Edit |

</details>

<details>
<summary><b>显存参考（Anima LoRA 1024，RTX 4090）</b></summary>

| 显存 | 配置 |
|------|------|
| ≥ 24 GB | 默认 |
| ≥ 16 GB | `gradient_checkpointing` |
| ≥ 12 GB | 梯度检查点 |
| ≥ 10 GB | + `blocks_to_swap=16` |
| ≥ 8 GB | + swap 24 + 缓存 TE + LoKr |

双参考训练通常从 **512×512** 起步；更高分辨率见 [VRAM 文档](docs/design/anima-edit-vram-resolution.md)。

</details>

<details>
<summary><b>Next Trainer 主线：仓库布局、FAQ、更新日志</b></summary>

- 仓库目录约定：[docs/repo-layout.md](docs/repo-layout.md)
- 整合包 v2.5.2→2.5.3：[docs/portable-upgrade-2.5.2-to-2.5.3.md](docs/portable-upgrade-2.5.2-to-2.5.3.md)
- 打标、torch 安装失败、路径嵌套等通用问题：见 [main 分支 README](https://github.com/wochenlong/lora-scripts-next/blob/main/README-zh.md)
- [CHANGELOG.md](CHANGELOG.md) · [NOTICE.md](NOTICE.md)

</details>

---

<p align="center"><sub>维护者：<b><a href="https://github.com/wochenlong">@wochenlong</a></b> · <a href="CONTRIBUTORS.md">贡献者</a></sub></p>

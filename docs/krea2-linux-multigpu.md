# Linux：Krea 2 多卡训练（`dev` / Musubi）

面向 **`dev` 分支**（Vue3 内测线）在 Linux 上用 **Musubi-Tuner** 训 **Krea 2 LoRA**，并启用 **多 GPU（Accelerate DDP）**。

| 项 | 说明 |
|----|------|
| 通道 | Git 分支 **`dev`**（含 [#229](https://github.com/wochenlong/lora-scripts-next/pull/229) 多卡启动器） |
| 引擎 | **Musubi**（独立 venv，与 Kohya 主环境隔离） |
| 上游 | [kohya-ss/musubi-tuner](https://github.com/kohya-ss/musubi-tuner)（官方示例本身用 `accelerate launch`） |
| Windows 整合包 | 多卡同样走前端「显卡设置」；本篇以 **Linux 源码 / 云主机** 为主 |

> 实现说明：训练阶段由 `mikazuki/musubi_backend/launcher.py` 调用 musubi venv 的  
> `python -m accelerate.commands.launch`；`gpu_ids` ≥ 2 时附加 `--multi_gpu --num_processes N`。  
> **缓存 latents / 文本编码器** 仍固定在**第一张**选中的 GPU（单进程），避免多卡抢写缓存。

---

## 1. 环境要求

- Linux + **NVIDIA 驱动**（建议 2 张及以上同架构 GPU；异构卡可能不稳定）
- Python **3.10**（与本仓库一致）
- CUDA / Torch 与 Musubi 安装选项一致（页内/CLI 常用 **`cu128`**）
- 磁盘：底模约 **35 GB**（DiT + TE + VAE）+ 数据集缓存 + 输出
- 网络：首次安装 Musubi 需访问 GitHub / PyPI / PyTorch wheel

确认 GPU：

```bash
nvidia-smi
# 应看到多张卡，例如 GPU 0 / GPU 1
```

---

## 2. 获取 `dev` 并启动 WebUI

```bash
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
git checkout dev
git pull

# 主环境安装（按你机器习惯；可用国内镜像）
# python -m venv .venv && source .venv/bin/activate
# pip install -r requirements.txt   # 或项目文档推荐的 setup 流程

bash run_gui.sh
# 国内镜像可选：USE_CN_MIRROR=1 bash run_gui.sh
```

浏览器打开 **http://127.0.0.1:28000**（或实例映射端口）。  
云主机（如 AutoDL）可参考 [docs/autodl-deploy.md](./autodl-deploy.md) 完成主环境与端口。

侧栏版本号应落在 **`2.9.x-beta.*`**（含多卡修复的 `dev` 提交之后）。

---

## 3. 安装 Musubi 引擎

Musubi **不能**并入主 `requirements.txt`，必须独立 venv。

### 方式 A：WebUI（推荐）

1. **设置 → 训练引擎 → Musubi → 安装**（或训练页选 Krea2 × Musubi 时按引导安装）
2. CUDA 口味选 **`cu128`**（与当前默认一致；勿与 Anima Fast 的 cu130 混为一谈）
3. 等待状态变为 **就绪 / ready**

### 方式 B：命令行

在仓库根目录：

```bash
python scripts/cli/install_musubi.py --cuda-extra cu128
```

安装完成后，常见布局类似：

```text
extensions/musubi_tuner/   # 或 vendor / 配置指定路径
  .venv/                   # musubi 专用 Python + accelerate + torch
  source/ 或 src/          # musubi-tuner 源码
```

---

## 4. 准备 Krea 2 底模

相对项目根（与 `gui.py` 同级）放置：

```text
sd-models/krea2/
  krea2.safetensors                 # DiT RAW
  qwen_image_vae.safetensors        # VAE
  qwen3_vl_4b.safetensors           # 文本编码器
```

训练页默认路径与上表一致。也可在页内「下载资源」拉取（若已提供条目）。  
**fp8**：若开 `fp8_base`，必须同时开 `fp8_scaled`（Krea2 硬约束）。

---

## 5. 数据集

推荐 Kohya 风格子目录（WebUI 会转成 musubi dataset toml）：

```text
train/
  10_character/
    xxx.png
    xxx.txt
  5_style/
    ...
```

目录名前缀数字为 `num_repeats`。打标可用本仓库数据集页 / WD14。

---

## 6. WebUI 多卡开训（主路径）

1. 打开 **训练**，选择：
   - 基础模型：**Krea 2**
   - 引擎：**Musubi**
   - 目标：**LoRA**
2. 填好 DiT / VAE / TE、数据集目录、输出名与训练步数等。
3. 若机器有 **≥ 2 张 GPU**，表单会出现 **「显卡设置」**：
   - **多选**要用的卡（例如 GPU 0 与 GPU 1）
   - 只选一张 = 单卡（仍走 `accelerate launch` 单进程）
4. 校验 → **开始训练**。
5. 到 **任务** 页查看三段流水线：
   1. `cache_latents`（单卡）
   2. `cache_text_encoder`（单卡）
   3. `train`（多卡时应出现 accelerate multi-GPU / 多 process）

可用另一终端观察：

```bash
watch -n 1 nvidia-smi
```

训练阶段两张卡都应有明显显存/利用率；若只有一张在动，检查是否只勾了一张卡，或 `dev` 是否尚未包含 #229。

### 有效 batch 怎么理解

多卡时 Accelerate DDP 通常使 **全局有效 batch ≈ 每卡 `train_batch_size` × GPU 数**（再乘梯度累积）。  
从单卡迁到多卡时，可酌情下调每卡 batch 或学习率，并以验证图为准。

---

## 7. 进阶：不经 WebUI 的 accelerate 命令（对照用）

WebUI 已代写 TOML 并编排 cache→train。若你在 musubi 目录手工复现（排障时有用），形态接近上游文档：

```bash
# 进入 musubi 根目录，并激活其 .venv
cd /path/to/musubi-tuner   # 以本机 extensions/musubi_tuner 等实际路径为准
source .venv/bin/activate

export CUDA_VISIBLE_DEVICES=0,1

# 先单卡完成 cache（示例参数按你的 toml 改）
python krea2_cache_latents.py --dataset_config /path/to/dataset.toml --vae /path/to/vae.safetensors --skip_existing
python krea2_cache_text_encoder_outputs.py --dataset_config /path/to/dataset.toml --text_encoder /path/to/te.safetensors --skip_existing

# 再多卡训练（与 WebUI 启动器等价思路）
accelerate launch --multi_gpu --num_processes 2 \
  --num_cpu_threads_per_process 1 --mixed_precision bf16 \
  krea2_train_network.py --config_file /path/to/train.toml
```

日常请优先用 WebUI，避免手工 TOML 与 GUI 字段不一致。

首次使用 Accelerate 也可在 musubi venv 内执行一次 `accelerate config`（本机、This machine、多 GPU）；**WebUI 路径会在命令行显式传 `--multi_gpu`，不依赖你是否跑过 config**。

---

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| 没有「显卡设置」 | 通常只有 **1** 张可见 GPU；检查 `nvidia-smi`、驱动、容器是否只挂了一张卡 |
| 多选了卡但只有一张在跑 | 确认已 `git pull` 到含 #229 的 `dev`；看训练任务命令是否含 `accelerate.commands.launch` 与 `--multi_gpu` |
| `fp8_scaled requires fp8_base` | 成对勾选 fp8_base + fp8_scaled，或都关掉 |
| Musubi 安装失败 | 查引擎安装日志；网络 / CUDA extra 是否匹配；可重试「修复」 |
| cache 很慢、训练才双卡 | **预期行为**：cache 只用第一张卡 |
| NCCL / 分布式超时 | 确认同机多卡、驱动正常；可试减少进程数或换更稳的驱动；日志留 Issue |

反馈 Issue 时请附：`dev` commit / 侧栏版本、`nvidia-smi`、所选 `gpu_ids`、任务详情里的 command 摘要与失败末几行日志。

---

## 9. 相关链接

- Issue：[feat(musubi): Krea2 多卡训练](https://github.com/wochenlong/lora-scripts-next/issues/228)
- PR：[#229](https://github.com/wochenlong/lora-scripts-next/pull/229)
- 引擎计划（维护者）：[docs/musubi-tuner-engine-plan.md](./musubi-tuner-engine-plan.md)
- AutoDL 主环境：[docs/autodl-deploy.md](./autodl-deploy.md)
- 上游 Krea2：[musubi-tuner docs/krea2.md](https://github.com/kohya-ss/musubi-tuner/blob/main/docs/krea2.md)

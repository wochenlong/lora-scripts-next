# Akatsuki Latent-Only 动作迁移实验反馈

这份文档总结了我们基于 `akatsuki-neo/anima-edit` 的 `train_latent.sh` 路线所做的第一轮 latent-only 动作迁移小实验。

这轮实验的目标比较收敛，主要是确认下面几件事：

- 在我们的本地 Windows 环境里，这条训练路线是否能完整跑通
- 产出的 LoRA 是否能正常保存并通过 safetensors 元数据验收
- 多参考图推理是否能正常加载这份 LoRA
- 在一个很小的动作迁移数据集上，低步数训练是否已经能看出编辑信号

## 环境信息

- 工作区：`<workspace_root>`
- 训练/推理时使用的私有仓库 clone：`<local_clone>/akatsuki-neo-anima-edit`
- 操作系统：Windows
- GPU：RTX 4090 24 GB
- 本轮实验使用的 Python 环境：`<workspace_root>` 下的本地 `venv`

使用到的基础模型权重：

- DiT：`<workspace_root>/sd-models/anima/anima-base-v1.0.safetensors`
- VAE：`<workspace_root>/sd-models/anima/qwen_image_vae.safetensors`
- Text Encoder：`<workspace_root>/sd-models/anima/qwen_3_06b_base.safetensors`

## 数据集情况

数据集压缩包来源：

- [anima-edit-action-transfer-12-akatsuki-vlm.zip](https://huggingface.co/datasets/windsingai/FLUX.1-Kontext-dev-dataset/blob/main/anima-edit-action-transfer-12-akatsuki-vlm.zip)

本地实验使用的数据目录：

- `<workspace_root>/data/anima-edit-action-transfer-12-akatsuki-vlm/1_action_transfer`

训练启动时传入的是它的父目录：

- `<workspace_root>/data/anima-edit-action-transfer-12-akatsuki-vlm`

数据格式如下：

- 目标图：`action_transfer_0000.png`
- 角色/source 参考图：`action_transfer_0000_ref.png`
- 动作/pose 参考图：`action_transfer_0000_ref1.png`
- 文本标注：`action_transfer_0000.txt`

这个数据集一共包含 12 条动作迁移样本，都是双参考图编辑格式。

本轮验收重点使用的样本是：

- source 角色：白色长袖上衣、深蓝色牛仔裤的金发女生
- pose 参考：竖劈高抬腿动作
- target：把 source 角色迁移到 pose 参考动作上的目标图

caption 是比较简单的编辑式描述，直接描述想要的变换结果。

## 训练实现

本地训练启动脚本：

- `run_akatsuki_latent_50steps.ps1`

它实际调用的是：

- `accelerate launch anima_train_network.py`

本轮实验使用的关键参数如下：

- `--train_data_dir <workspace_root>/data/anima-edit-action-transfer-12-akatsuki-vlm`
- `--output_dir <workspace_root>/output/anima-edit-action-transfer-12-akatsuki-latent-50steps`
- `--output_name anima-edit-lora-action-transfer-12-akatsuki-latent-50steps`
- `--network_module networks.lora_anima`
- `--network_dim 128`
- `--network_alpha 128`
- `--network_train_unet_only`
- `--learning_rate 1e-4`
- `--optimizer_type AdamW`
- `--lr_scheduler constant`
- `--max_train_steps 50`
- `--train_batch_size 1`
- `--mixed_precision bf16`
- `--save_precision bf16`
- `--resolution 1024,1024`
- `--enable_bucket`
- `--min_bucket_reso 512`
- `--max_bucket_reso 1024`
- `--bucket_reso_steps 64`
- `--caption_extension .txt`
- `--anima_multi_image_edit`
- `--gradient_checkpointing`
- `--vae_disable_cache`
- `--attn_mode torch`
- `--save_every_n_steps 25`

这轮实验是刻意做成 smoke-scale 的验证，不是收敛型训练。

## 训练结果

输出目录：

- `<workspace_root>/output/anima-edit-action-transfer-12-akatsuki-latent-50steps`

实际产物：

- `anima-edit-lora-action-transfer-12-akatsuki-latent-50steps-step00000025.safetensors`
- `anima-edit-lora-action-transfer-12-akatsuki-latent-50steps-step00000050.safetensors`
- `anima-edit-lora-action-transfer-12-akatsuki-latent-50steps.safetensors`

训练耗时观察：

- 50 steps 总耗时大约 3 小时 58 分钟

单步耗时观察：

- 每 step 大约 285 到 292 秒

最终日志里的 loss：

- 大约 `avr_loss=0.0582`

## Safetensors 验收

我们使用下面这个脚本做 checkpoint 元数据验收：

- `<workspace_root>/.runtime/anima_action_transfer/verify_akatsuki_latent_safetensors.py`

step 25 的结果：

- 大小：`367110616` bytes
- tensor 数量：`840`
- `ss_steps=25`
- `ss_network_dim=128`
- `ss_network_alpha=128.0`

final 的结果：

- 大小：`367110616` bytes
- tensor 数量：`840`
- `ss_steps=50`
- `ss_network_dim=128`
- `ss_network_alpha=128.0`

从 checkpoint 格式和 metadata 角度看，这份 LoRA 是健康的。

## 推理实现

本地推理包装脚本：

- `<workspace_root>/.runtime/anima_action_transfer/run_akatsuki_latent_infer.ps1`

它内部调用：

- `anima_minimal_inference.py`

推理时使用：

- 本地 Anima 的 DiT、VAE、Qwen3 text encoder
- 两张参考图：
  - `*_ref.png`
  - `*_ref1.png`
- 对应样本的 `*.txt` caption
- 训练产出的 LoRA，通过 `--lora_weight` 加载

本轮验收尝试过几种推理设置：

- 原本更接近目标使用场景的设置：`1024` 分辨率，`30 infer steps`
- 为了跑通验收而降低的 smoke 设置：
  - `512` 分辨率，`8 infer steps`
  - `256` 分辨率，`1 infer step`

在验收阶段，我们也测试了 `attn_mode=xformers`，因为 `torch` attention 非常慢。

## 遇到的问题

### 1. latent-only 多参考编辑模式训练非常慢

即使在 4090 上：

- 50 steps 训练也接近 4 小时
- 推理也同样很慢

本轮验收观察到的推理速度大致是：

- `1024` / `30 steps`：慢到几乎不适合正常迭代验收
- `512` / `8 steps`：仍然明显过慢
- `256` / `1 step` / `xformers`：单步去噪加解码也要约 4 分钟

这会让实验迭代和对比验证都比较困难。

### 2. Windows 下反复出现 Triton 缺失告警

我们多次看到：

- `ModuleNotFoundError: No module named 'triton'`

从现象上看，这更像是性能告警，而不是直接导致训练失败的原因，但它说明当前 Windows 环境没有走到最快的执行路径。

### 3. PowerShell 对 stderr 的处理会干扰推理判断

在最初的推理包装里，因为 PowerShell 使用了 `$ErrorActionPreference = "Stop"`，而 xformers 的 warning 又会写到 stderr，所以最开始看起来像是推理“立刻失败”了。

但把 stdout/stderr 分开看之后，可以确认 Python 进程本身是正常继续跑的。

### 4. 我们本地 watcher 对 checkpoint 文件名的预期不对

我们本地最初的 watcher 以为中间产物会命名成：

- `...-000025.safetensors`

但训练实际输出的是：

- `...-step00000025.safetensors`

这属于我们本地集成逻辑的问题，不是训练本身的问题。后面我们已经按实际输出文件名修正了 watcher。

### 5. inference 的 save_path 行为和我们最初预期略有不同

`anima_minimal_inference.py` 看起来会把 `save_path` 更像目录一样使用，并在里面再创建带时间戳的文件。

理解这个行为之后就可以继续用，但它和我们最初包装脚本里以为的“直接输出到某个 png 文件”不完全一样。

## 图片结果说明

我们为这轮验收生成了：

- step 25 的验收图
- step 50/final 的验收图
- 对比 contact sheet

主对比图：

- [akatsuki_latent_25_vs_50_256x1_contact_sheet.png](D:/ai/lora-scripts-next/.runtime/anima_action_transfer/akatsuki_latent_25_vs_50_256x1_contact_sheet.png)

这张图从左到右分别是：

- `source ref`：原始 source 角色图
- `pose ref`：动作/姿态参考图
- `target`：期望编辑结果
- `latent 25 256x1`：step 25 LoRA 在一个很小的验收推理设置下的输出
- `latent 50 256x1`：final/step 50 LoRA 在相同设置下的输出

为了方便查看，这里直接放入对比图：

![akatsuki latent 25 vs 50 contact sheet](D:/ai/lora-scripts-next/.runtime/anima_action_transfer/akatsuki_latent_25_vs_50_256x1_contact_sheet.png)

这张对比图里使用到的两张单独验收图分别是：

- step 25：
  [20260608-200514-069_606120_.png](D:/ai/lora-scripts-next/.runtime/anima_action_transfer/akatsuki_latent_25steps_0000_256x1/20260608-200514-069_606120_.png)
- step 50：
  [20260608-195918-968_606120_.png](D:/ai/lora-scripts-next/.runtime/anima_action_transfer/akatsuki_latent_attn_xformers.png/20260608-195918-968_606120_.png)

从 25-step 和 50-step 的视觉结果来看，我们的结论是：

- 它不是纯噪声
- LoRA 的确被成功加载，并对推理链路产生了影响
- 但它还没有表现出明确的“单角色动作迁移编辑”能力
- 更接近“在复述/并列参考输入”，而不是把 source 角色真正迁移成 target 那种动作结果

换句话说：

- 这条路线的训练和推理链路已经被我们验证为可以跑通
- 但在这个数据集上，25 或 50 steps 还不足以证明它已经学会了我们想要的编辑行为

## 当前判断

我们认为至少有三种可能性同时存在：

1. `50` steps 对这个任务来说就是太少了
2. latent-only 路线本身对这个动作迁移任务不够强
3. 当前 inference 设置过慢、过粗，导致一些很弱的早期训练信号不容易被清楚观察出来

所以目前我们不觉得可以直接下结论说“这条方法失败了”，但也不觉得当前结果可以被描述成“已经拟合出有效编辑能力”。

我们更倾向于这样表述：

- 这轮实验已经成功验证了 pipeline
- 但还没有成功验证任务质量

## 建议的下一轮实验

如果继续往下做，我们更建议：

- 先做一个 `200` 到 `300` steps 的中间实验，而不是直接跳到 `1000`
- 保持固定的验收样本和固定 seed
- 保留 `100`、`200` 和 final checkpoint
- 尽量使用更快的推理路径，否则当前验收速度太慢，不利于健康迭代

这样更容易区分下面两种情况：

- “模型只是还没训够”

和

- “latent-only 路线在这个数据集上并没有学到想要的编辑行为”

## 我们这边的相关本地文件

这轮实验相关的本地文件包括：

- 训练启动脚本：
  - `<workspace_root>/.runtime/anima_action_transfer/run_akatsuki_latent_50steps.ps1`
- 推理包装脚本：
  - `<workspace_root>/.runtime/anima_action_transfer/run_akatsuki_latent_infer.ps1`
- 25-step watcher：
  - `<workspace_root>/.runtime/anima_action_transfer/watch_akatsuki_latent_25step_eval.ps1`
- final watcher：
  - `<workspace_root>/.runtime/anima_action_transfer/watch_akatsuki_latent_50steps_and_eval.ps1`
- safetensors 验收脚本：
  - `<workspace_root>/.runtime/anima_action_transfer/verify_akatsuki_latent_safetensors.py`
- 主对比图：
  - `<workspace_root>/.runtime/anima_action_transfer/akatsuki_latent_25_vs_50_256x1_contact_sheet.png`

## 简短结论

在我们的 Windows + RTX 4090 环境下，这条 `train_latent.sh` 路线面对这个 12 样本动作迁移数据集时：

- 可以成功训练
- 可以产出有效的 LoRA checkpoint
- 可以跑多参考图推理
- 训练和推理都非常慢
- 在 25 或 50 steps 时，还没有出现令人信服的动作迁移拟合结果

我们当前的看法是：低步数很可能是原因之一，但不太像唯一原因。

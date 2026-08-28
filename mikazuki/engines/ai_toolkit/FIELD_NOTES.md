# FIELD_NOTES — ai-toolkit pack

> 验证矩阵与踩坑流水随 bump 更新；过期的「已验证」比没有更害人。

## 验证矩阵

| 日期 | 上游 commit | 变体 | 环境 | 结果 |
| --- | --- | --- | --- | --- |
| 2026-08-28 | 5497a001cb8752c665f93907a0393fc612116fd5 | klein-4b / klein-9b | GB10 (aarch64, cu130) | 仅静态：adapter/preflight/routes 单测 + dry-run 出 yaml。**未跑真机训练**（待 GPU 窗口） |

## 踩坑流水

- Klein TE/VAE 默认从 HF 拉（Qwen/Qwen3-4B·8B、ai-toolkit/flux2_vae）；**上游没有 config 键覆盖为本地路径**（`flux2_klein_te_path` 是类属性，2026-08-28 快照）。需要离线/自定义 TE 时打 patch（候选：`model_kwargs.flux2_klein_te_path` 透传）。
- 上游无 Klein example yaml；官方默认取自上游 UI（options.tsx）：quantize+qfloat8、low_vram 建议开、timestep_type=weighted、sampler=flowmatch、`model_kwargs.match_target_res=false`。
- `run.py` 以 `os.getcwd()` 为 import root → launch 必须 cwd=toolkit_root（launcher 已处理，PYTHONPATH 同步镜像）。
- `get_model.py` 会遍历 `extensions/` 与 `extensions_built_in/`——源码快照必须保留空的 `extensions/` 目录（installer 已兜底创建）。
- torch 不在上游 requirements 里，安装时须先从 CUDA index 装 torch/torchvision 再装 requirements（environment.install_environment 两段式）。
- **2026-08-28 GB10 实装命中**：`dgx_requirements.txt` 经 `-r` 嵌套钉的 `torchcodec==0.9.1` 无 linux aarch64 wheel，安装器递归剥离该 pin（`prepare_requirements`）；torchcodec 仅视频/manager 用，Klein 图像路径不 import。已提炼为 KNOWN_PITFALLS P5。
- **2026-08-28 UI 命中**：schema 初版 DiT 字段用 `pretrained_model_name_or_path`，与 kohya 撞名，SDXL 配置被 carry-over 进 Klein 页。改为引擎专属键 `dit`（照 krea2 先例）+ `dit` 进 `CROSS_SCHEMA_DENY_KEYS`。已提炼为 KNOWN_PITFALLS P6。
- **2026-08-28 资产下载**：HF `black-forest-labs/FLUX.2-klein-base-{4B,9B}` **未 gate**，根目录有单文件 DiT；ModelScope 有同名镜像同文件——DiT 资产双源可下。VAE 用上游约定：`<name_or_path>/ae.safetensors` 存在即本地消费（flux2_model.py），故 VAE 资产落 `sd-models/klein/ae.safetensors` 与 DiT 同目录；`ai-toolkit/flux2_vae` 官方仓无 ModelScope 镜像，但社区镜像 `KanKanKan/flux2-vae`（flux2-vae.safetensors）已验证为 ae 单文件键布局（Range 拉 header 确认 `decoder.up.0.block.0.conv1.bias`），MS 源已配上（2026-08-28）。另纠正：VAE 有本地覆盖键 `model.vae_path`（ModelConfig），此前调研漏看；目前用同目录约定即可，未接 schema。**VAE 登记为必需资产**（2026-08-28：xet 401 实证运行时自动拉取不可靠，必须先本地就位）。**TE（Qwen3-4B/8B）未登记进下载组件**：上游无本地覆盖 config 键，下了也喂不进去，待 TE 覆盖 patch 后补登。
- **2026-08-28 训练冒烟命中**：快照漏带根目录 `info.py`（被 `toolkit/metadata.py` 顶层 import），训练进程 `No module named 'info'`。已补 `INCLUDE_TOP_LEVEL` + 快照完整性测试，提炼为 KNOWN_PITFALLS P7。**修复后需点「重新安装」重拷源码。**
- **2026-08-28 训练冒烟命中 2**：`torchaudio` 上游未声明但 `toolkit/config_modules.py:7` 顶层 import，训练进程 `No module named 'torchaudio'`。安装器 torch 阶段补装 torch torchaudio torchvision 三件套，audit 探测同步覆盖。
- **2026-08-28 训练冒烟命中 3**：VAE（`ai-toolkit/flux2_vae`，恰好 3 个文件）运行时自动从 HF 拉取时 hf-xet CAS 后端 401（`run.py` 默认开 xet；代理/镜像环境高发）。launcher 默认 `HF_HUB_DISABLE_XET=1` 回退普通 CDN；本地有 `ae.safetensors`（资产组件下载）则完全不走 HF。
- Linux aarch64（DGX Spark）用 `dgx_requirements.txt`，别用成 win_arm64 的 `spark_requirements.txt`。
- 进度/loss 日志解析未做：Toolkit stdout 格式要真跑训练才能摸，冒烟后回来补（Task 详情页指标提取依赖它）。

## 待办：日志 / sample / tensorboard 接入（详见外层调研文档 docs/issue-299-plan.md）

冒烟时**必须留存证据**：① 完整 stdout 样例（含 tqdm 进度行、loss 行）；② `training_folder/<name>/` 目录树（samples 落点、tensorboard event 文件位置）；③ 采样预览图的实际文件名规律。回填本文件后再写 `ai_toolkit/progress.py`。

## 冒烟清单（GPU 窗口时执行）

1. 安装：`POST /api/engines/ai-toolkit/install {"dry_run": false}` → state=ready、audit 全绿。
2. klein-4b-lora：小数据集（~10 张）+ max_train_steps=20 + 采样预览开 → 出 LoRA safetensors + 预览图。
3. klein-9b-lora：同上（量化默认开）。
4. 编辑数据集：train_data_dir + control_data_dirs[] 同名配对 → 训练正常消费 control 图。
5. 记录 stdout 日志样例 → 回填进度解析。

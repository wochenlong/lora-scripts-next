# musubi-tuner 引擎接入实现计划（vendor）

> 目标：把 [kohya-ss/musubi-tuner](https://github.com/kohya-ss/musubi-tuner) 作为**新的训练引擎**接入本仓库，首期支持 **Krea 2 LoRA 训练**（`krea2-lora`），架构上为后续其他 musubi 模型铺路。
> 模式：完全复用 `mikazuki/engines/anima_fast/` 已验证的「独立源码树 + 独立 venv + 配置适配器」插件模式，不动主环境。

## 0.1 范围与路线图

- 本工具定位为**图像型训练工具**，musubi 的视频模型（HunyuanVideo / HV1.5 / Wan / FramePack / Kandinsky 5）**不在接入范围内**。
- 路线：先把插件骨架 + Krea 2 跑通，再按相同模式逐个尝试其余**图像**模型。musubi 侧候选（按预期工作量排序）：
  1. `krea2-lora`（Krea 2）—— 首期，本计划覆盖
  2. `zimage-lora`（Z-Image）、`qwen-image-lora`（Qwen-Image）—— 与 Krea2 同属「单 DiT + 单/双文本编码器」形态，adapter 主要换脚本名、参数字段和 network_module
  3. `flux-kontext-lora`（FLUX.1 Kontext，图像编辑）、`flux2-lora`（FLUX.2）—— 参数字段更多（双文本编码器等）
  4. `hidream-o1-lora`、`ideogram4-lora` —— 备选，按需求再定
- 每加一个模型 = 新增 schema ts + adapter 字段白名单/约束 + launcher 脚本名 + 预设，骨架（settings/environment/process 三段式/api 分支模式）不变。

## 0. 背景与结论

- musubi-tuner 依赖与主环境**硬冲突**：accelerate 1.6.0（主环境 0.33.0）、transformers 4.57.6（主环境 4.51.3）、numpy 不设上限（主环境钉死 1.26.4）。**必须独立 venv**，不可能并入主 `requirements.txt`。
- 本仓库已有两条引擎路径：
  - 标准路径：`mikazuki/app/api.py:110` 的 `trainer_mapping` → `scripts/dev|stable/*.py` → `mikazuki/process.py:98` 的 `build_accelerate_train_command()`（共用主 venv）。
  - 插件路径：`mikazuki/engines/anima_fast/`（settings/installer/launcher/adapter/preprocess 五件套），独立 venv、独立源码树、独立 Python 启动。**musubi 走这条。**
- musubi-tuner 侧关键事实（已核实源码）：
  - 根目录 `krea2_train_network.py` 是薄壳，`from musubi_tuner.krea2_train_network import main`，需 `pip install -e .` 或 PYTHONPATH 指向 `src/`。
  - 训练入口直接 `python xxx_train_network.py --config_file a.toml`（内部自建 Accelerator，无需 accelerate launch 包装）；`--config_file`/`--dataset_config` 解析在 `src/musubi_tuner/training/parser_common.py:37,43`。
  - 数据集 toml 格式**与 kohya 不兼容**：`[[datasets]]` + `image_directory` / `cache_directory` / `num_repeats`（见 musubi `docs/dataset_config.md`），不吃 kohya 的 `10_概念名` 子目录约定。
  - 缓存是**训练前的独立步骤**：`krea2_cache_latents.py` + `krea2_cache_text_encoder_outputs.py`，写入 dataset toml 指定的 `cache_directory`。
  - Krea2 特有硬约束（`src/musubi_tuner/krea2_train_network.py:74-95`）：`--fp8_base` 必须搭配 `--fp8_scaled`；`--turbo_dit` 与 `--blocks_to_swap` 互斥；模型路径拆分传 `--dit` / `--vae` / `--text_encoder`（Qwen3-VL）。
  - network_module 为 `musubi_tuner.networks.lora_krea2`（`src/musubi_tuner/networks/lora_krea2.py`，默认 target 全部 264 个 Linear，`exclude_patterns`/`include_patterns` 走 network_args）。
  - 采样图输出 `output_dir/sample`（`training/trainer_base.py:854`），与现有前端预览扫描约定一致；tensorboard tag `loss/current`/`loss/average` 与 `mikazuki/utils/task_insights.py:20` 的 `LOSS_TAGS` 兼容。

## 1. 总体架构

```
WebUI (krea2-lora schema)
  → POST /api/train (model_train_type="krea2-lora")
  → mikazuki/app/api.py            分支到 musubi backend
  → mikazuki/engines/musubi/
      adapter.py      GUI 字段 → musubi config toml + dataset toml
      settings.py     RuntimeConfig（root/venv python/目录发现）
      launcher.py     build_launch_spec(cache) + build_launch_spec(train)
      installer.py    venv 创建 + uv pip install -e
      preprocess.py   串行跑 cache_latents → cache_text_encoder_outputs
  → vendor/musubi-tuner/.venv/Scripts/python.exe
      krea2_cache_latents.py --dataset_config d.toml ...
      krea2_cache_text_encoder_outputs.py --dataset_config d.toml ...
      krea2_train_network.py --config_file train.toml
  → TaskManager 统一接管子进程（日志 SSE / 停止 / tensorboard loss / sample 预览）
```

## 2. 任务分解

### 2.1 vendor 引入

- [ ] `.gitmodules` 新增 `vendor/musubi-tuner` submodule，pin 到上游 release tag（当前 0.3.4），与 `vendor/sd-scripts` 同等待遇。
- [ ] `install.ps1` / `install.bash` / `setup_environment.py`：可选开关（默认不装，避免拖慢主安装）；勾选后创建 `vendor/musubi-tuner/.venv` 并 `uv pip install -e ".[cu128]"`（cu124/cu128/cu130/cu132 按主环境 CUDA 探测结果选择，musubi `pyproject.toml:29-45`）。
- [ ] Windows 注意：`frontend/dist` 同款 EOL 问题不涉及，但 submodule 更新要走代理（见工作区根 AGENTS.md）。

### 2.2 `mikazuki/engines/musubi/` 新包（仿 `mikazuki/engines/anima_fast/`）

- [ ] `settings.py`：`RuntimeConfig(musubi_root, python, output_dir, logging_dir, cache_dir, hf_home)`；配置文件 `config/musubi_backend.toml`；kill switch 环境变量 `LORA_ENABLE_MUSUBI=0`；discovery 顺序 = 配置文件 → `MUSUBI_ROOT` 环境变量 → `vendor/musubi-tuner`（参照 `mikazuki/engines/anima_fast/settings.py`）。
- [ ] `launcher.py`：`build_launch_spec(runtime, script, args, task_id, gpu_ids)` → `LaunchSpec(command=[venv_python, root/script, *args], cwd=root, env)`；env 处理照 `mikazuki/engines/anima_fast/launcher.py`：`PYTHONNOUSERSITE=1`、`PYTHONUNBUFFERED=1`、去掉主项目 `PYTHONPATH`、按需注入 `HF_HOME`/`CUDA_VISIBLE_DEVICES`；**额外**：若未 `pip install -e`，注入 `PYTHONPATH=<root>/src`。
- [ ] `adapter.py`：GUI payload → 两个 toml：
  - train toml 字段白名单：`dit`、`vae`、`text_encoder`、`output_dir`、`output_name`、`max_train_epochs`、`max_train_steps`、`train_batch_size`、`learning_rate`、`optimizer_type`、`optimizer_args`、`lr_scheduler`、`lr_warmup_steps`、`mixed_precision`、`gradient_checkpointing`、`network_module`（固定 `musubi_tuner.networks.lora_krea2`）、`network_dim`、`network_alpha`、`network_args`、`sample_prompts`、`sample_every_n_epochs`、`sample_at_first`、`seed`、`logging_dir`、`log_with`、`save_precision`、`fp8_base`、`fp8_scaled`、`blocks_to_swap`、`timestep_sampling`、`discrete_flow_shift` 等。
  - 约束校验（产生 `_training_warnings`，仿 `anima_backend/adapter.py` 的 LOKR warning 模式）：
    - `fp8_base=true` 且 `fp8_scaled` 未开 → 自动补 `fp8_scaled=true` + warning；
    - `turbo_dit=true` 且 `blocks_to_swap>0` → 拒绝并提示二选一；
    - Windows 上 `--compile` 提示 Triton 限制（同 `api.py:158` 的 torch_compile 处理）。
  - dataset toml 生成：`train_data_dir` + kohya `N_name` 子目录约定 → 逐子目录展开为 `[[datasets]]` 条目（`image_directory`、`num_repeats=N` 从目录名解析、`caption_extension`），`cache_directory` 自动分配 `<cache_dir>/<dataset_hash>/`（每个 dataset 必须不同，musubi 硬性要求）。
- [ ] `preprocess.py`：按序创建两个 cache 子任务（复用 `TaskManager`），全部成功后才创建训练任务；cache 目录存在且非空时跳过（增量缓存交给 musubi 自己判断）。
- [ ] `installer.py` / `preflight.py`：仿 anima_fast，检查 venv 存在、torch CUDA 可用、`import musubi_tuner` 成功。

### 2.3 `mikazuki/process.py` 启动链路

- [ ] 新增 `run_musubi_train(toml_path, runtime, gpu_ids, metadata)`（仿 `run_anima_fast_train`，`process.py:290`）：三段式流水线 `cache_latents → cache_te → train`，每段都是 `tm.create_task()` 接管的子进程，前一段 rc!=0 则终止并标记失败；task_metadata `backend: "musubi"`。

### 2.4 `mikazuki/app/api.py` 接线

- [ ] `model_train_type == "krea2-lora"` 分支：不走 `trainer_mapping`，走 musubi backend（参考 anima_fast 的分支方式）。
- [ ] `_PATH_FIELDS`（`api.py:149`）补充 `dit`、`text_encoder`（`vae` 已存在）做路径分隔符归一化。
- [ ] `get_sample_prompts()`（`api.py:210`）：musubi prompt 文件格式与 kohya 基本一致（每行一个 prompt，`--w`/`--h`/`--d`/`--s`/`--l` 选项），沿用现有生成逻辑，仅需确认 Krea2 默认值（1024、cfg 4.5 参照 anima 默认）。
- [ ] 环境/状态 API：新增 musubi runtime status 端点（仿 anima_fast 的 environment.py / extension_state.py），前端据此显示「插件已就绪 / 未安装 / 安装中」。

### 2.5 前端

- [ ] `mikazuki/schema/krea2-lora.ts`：新表单 schema（`load_schemas()` 自动拾取，`api.py:178`）。字段分区参照 `anima-lora-fast.ts`：模型（dit/vae/text_encoder）、数据、训练、网络（dim/alpha/exclude_patterns）、显存（fp8_base+fp8_scaled/blocks_to_swap/gradient_checkpointing）、采样预览。
- [ ] `config/presets/` 新增 Krea2 预设 toml（rank 32/alpha 32，官方推荐配置，见 `lora_krea2.py` 头部注释）。
- [ ] 前端 i18n 词条（中英）+ 训练类型选择器出现「Krea 2 LoRA」；未安装插件时显示安装引导（复用 anima-fast 页的引导组件模式）。
- [ ] `frontend/dist` 产物提交前 `git add --renormalize`（见根 AGENTS.md）。

### 2.6 监控与日志

- [ ] 实测 `task_insights.py:124,130` 的 tqdm 正则（`steps: x%|...| a/b`、`epoch a/b`）对 musubi 输出的匹配情况，不匹配则扩展正则。
- [ ] tensorboard `LOSS_TAGS` 已兼容，实测确认 `loss/average` 有数据。
- [ ] sample 预览：确认前端扫描 `output_dir/sample` 能拿到 musubi 的命名（`output_name_e000001_000123.png` 之类）。

### 2.7 安装/打包/更新脚本

- [ ] `install.ps1` / `install.bash` 加 `--with-musubi` 可选步骤。
- [ ] portable 打包（`build-scripts/`）：musubi venv 是否进整合包需单独决策（体积 +数 GB）；不进包则提供 `scripts/cli/install_musubi.bat/.sh`（仿 `install_anima_fast.*`）。
- [ ] `update_lora_gui.sh` 处理 submodule 更新。

### 2.8 测试

- [ ] `tests/`：adapter 单测（字段映射、fp8/turbo 约束、dataset toml 生成、`N_name` 目录名解析）；launcher spec 单测（env、PYTHONPATH）；参照现有 anima adapter 测试。
- [ ] 端到端冒烟：小数据集（10 张）跑通 cache→训练 2 step→出 sample 图→监控页有 loss 曲线。

## 3. 风险与注意点

| 风险 | 应对 |
|---|---|
| musubi dataset 格式与 kohya 不兼容，用户已有 kohya 式数据目录 | adapter 层全自动转换，用户无感；文档注明差异 |
| cache 预处理是三段流水线，任务状态/失败定位更复杂 | 每段独立 task + metadata 关联父子任务； preprocess 失败信息直接透出 |
| musubi 上游迭代快，API/参数可能变 | submodule pin tag，升级单独走流程；adapter 白名单之外字段只 warning 不拦截 |
| Krea2 需要 Qwen3-VL 文本编码器（4B）+ DiT + VAE 三个模型文件 | schema 给三个独立路径字段 + HF 自动下载说明；预设文档列模型清单 |
| portable 包体积 | musubi 做成可选插件，不进默认整合包 |
| Windows fp8/`--compile` 限制 | adapter 自动降级 + warning，与现有 torch_compile 处理一致 |

## 4. 验收标准

1. WebUI 选「Krea 2 LoRA」，填模型三件套 + 数据目录，点开始训练后：自动建 venv（首次）、自动跑两段 cache、自动进训练。
2. `/train-monitor` 显示进度条、step 耗时、loss 曲线；`output_dir/sample` 预览图出现在任务详情。
3. 训练产物为标准 safetensors LoRA，可被 ComfyUI/A1111 加载。
4. 主环境 sd-scripts 训练回归无影响（`LORA_ENABLE_MUSUBI` 默认开但 musubi 未安装时不影响任何现有功能）。

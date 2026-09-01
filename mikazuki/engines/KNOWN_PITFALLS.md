# 已知坑库（引擎适配）

> 机器友好格式，适配任务第 7 步逐条比对。命中且判定确定 → 直接打现成补丁/绕法；
> 不确定 → 记 FIELD_NOTES 待人工。每条：症状模式 / 检测规则 / 现成补丁或绕法 / 来源。
> 新坑从各 pack 的 FIELD_NOTES「踩坑流水」提炼回填。

## P1. flash-attn Linux wheel 与上游依赖声明冲突

- 症状：上游 `pyproject.toml` 声明的 flash-attn 在本机 CUDA/torch 组合下无预编译 wheel，安装卡源码编译数小时或失败。
- 检测：上游依赖含 `flash-attn` 且目标平台 Linux；比对本机 torch/CUDA 与可用 wheel（如 mjun0812/flash-attention-prebuild-wheels）。
- 绕法：由项目按平台/架构显式选择预编译 wheel，source 包使用 `--no-deps` 安装。现成实现：`mikazuki/engines/anima_fast/environment.py` `flash_attn_dependency_target`。
- 来源：anima_fast pack。

## P2. 可选/平台限定依赖把安装拖死

- 症状：上游声明的可选运行时依赖（掩膜/可视化/平台限定包）在目标平台装不上，整个 `uv pip install` 失败。
- 检测：安装日志失败包名不在训练链路 import 里。
- 绕法：不要安装上游混合依赖表；项目显式维护训练闭包，并用 `--no-deps` 安装 source 包。现成实现：anima_fast `environment.py` `anima_pip_dependency_targets`。

### bitsandbytes 暂无 CUDA 13.2 binary

- bitsandbytes 0.49.2 的 Linux wheel 最高只带 `libbitsandbytes_cuda130.so`，在 torch cu132 下直接使用 AdamW8bit 会报缺少 `libbitsandbytes_cuda132.so`。
- Linux aarch64 暂时由 Anima Fast launcher 设置 `BNB_CUDA_VERSION=130`，复用包内 cuda130 backend；torch 和 FlashAttention 仍保持 cu132。
- 这是临时兼容方案，不是长期 ABI 承诺。bitsandbytes 发布可用 cu132 binary 后，应删除 launcher override 并增加对应 native optimizer smoke。
- 来源：anima_fast pack。

## P3. 子进程 PYTHONPATH / 编码污染

- 症状：引擎 venv 的 Python 启动后 import 到主项目的包，或 Windows 中文 console 下训练脚本输出乱码/崩溃。
- 检测：子进程 `sys.path` 含主项目路径；`PYTHONPATH` 环境变量非空；Windows 上 stdout 编码非 UTF-8。
- 绕法：launcher 构造 env 时剥离主项目 PYTHONPATH、设 `PYTHONNOUSERSITE=1`、`PYTHONUNBUFFERED=1`，按需注入 `PYTHONIOENCODING=utf-8`；未 `pip install -e` 时注入 `<root>/src`。现成实现：`mikazuki/engines/musubi/launcher.py`。
- 来源：musubi pack。

## P4. LyCORIS 版本 dtype 坑（LoKr/DoRA bf16）

- 症状：lycoris-lora 特定版本下 LoKr/DoRA + bf16 训练 dtype 不对齐报错或 loss=nan。
- 检测：`importlib.metadata.version("lycoris-lora")` 命中问题版本，且 algo 为 lokr（含 network_args `algo=lokr`）。
- 绕法：monkey-patch 前向修正 dtype。现成实现：`mikazuki/anima_backend/lycoris_patch.py` `patch_lokr_dora_bf16_forward`。
- 来源：kohya/anima 侧（随 kohya pack）。

## P5. 上游 pin 的依赖在目标平台无 wheel（含 `-r` 嵌套钉版）

- 症状：`uv pip install -r requirements*.txt` 报 "no wheels with a matching platform tag"，且 pin 藏在上游用 `-r` 嵌套引用的基础清单里（如 ai-toolkit 的 `dgx_requirements.txt` → `requirements_base.txt` 里的 `torchcodec==0.9.1` 无 linux aarch64 wheel）。
- 检测：失败包名确认不在目标训练链路 import 里（torchcodec 仅用于视频/manager，Klein 图像路径不 import）。
- 绕法：安装期递归剥离平台无 wheel 的 pin（含 `-r` 引用文件的重写），记日志。现成实现：`mikazuki/engines/ai_toolkit/environment.py` `prepare_requirements`。
- 来源：ai_toolkit pack（2026-08-28，GB10 aarch64 实装命中）。

## P6. schema 键名撞车：跨引擎配置被前端 carry-over 泄漏

- 症状：从 kohya（SDXL）页面切到插件引擎页面，底模路径等同名字段被自动带进新表单（如 SDXL 底模路径出现在 Klein 的 DiT 目录字段）。
- 检测：插件 schema 的字段键名与 kohya 方言同名但语义不同（路径指向的模型族不同）；机制是 `frontend/src/training/params.ts` `pickCarryOverFields` 按同名键跨 schema 继承。
- 绕法：插件 schema 对引擎专属资产路径用**引擎自己的键名**（先例：krea2 用 `dit`/`vae`/`text_encoder`，不与 kohya 的 `pretrained_model_name_or_path` 撞名）；已撞名且确实不该跨界的键加进 `CROSS_SCHEMA_DENY_KEYS`（如 `dit`）。
- 来源：ai_toolkit pack（2026-08-28，klein-lora schema 初版用 `pretrained_model_name_or_path` 撞名，实机操作命中）。

## P7. 源码快照漏带仓库根目录的隐式顶层模块

- 症状：安装后训练进程 `ModuleNotFoundError: No module named '<x>'`，`<x>` 是上游仓库根目录的散装 `.py`（如 ai-toolkit 的 `info.py`，被 `toolkit/metadata.py` 以 `from info import ...` 顶层导入），包目录（`toolkit/` 等）grep import 路径时漏掉它。
- 检测：快照装完先静态扫 `grep -rn "^from <name> import\|^import <name>"` 对根目录每个散装 `.py`；或冒烟跑训练入口即现形。
- 绕法：installer 的 `INCLUDE_TOP_LEVEL` 补上该文件，重装/修复即可。现成实现：`mikazuki/engines/ai_toolkit/installer.py`（含快照完整性测试）。
- 来源：ai_toolkit pack（2026-08-28，GB10 首次训练冒烟命中）。

## P8. 训练进程运行时自动下载不可信

- 症状：资产没本地化时，训练进程自己触网下载，在代理/镜像环境下失败且报错位置远离根因（hf-xet CAS 401、HF 直连被重置）。
- 检测：grep 上游训练入口/模型加载路径里的 `snapshot_download`/`from_pretrained`/`hf_hub_download`；凡训练路径能触到网络的都算命中。
- 绕法：资产一律登记进下载组件 + preflight 硬门槛，训练进程不碰网络；launcher 默认关 xet（`HF_HUB_DISABLE_XET=1`）。镜像源可用性必须实测：probe API + Range 拉 safetensors header 验键布局，仓名不算数。现成实现：`mikazuki/engines/ai_toolkit/launcher.py`、ai_toolkit 资产登记/preflight。
- 来源：ai_toolkit pack（2026-08-28，hf-xet CAS 401 与 TE 运行时下载两次实证）。

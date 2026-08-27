# 已知坑库（引擎适配）

> 机器友好格式，适配任务第 7 步逐条比对。命中且判定确定 → 直接打现成补丁/绕法；
> 不确定 → 记 FIELD_NOTES 待人工。每条：症状模式 / 检测规则 / 现成补丁或绕法 / 来源。
> 新坑从各 pack 的 FIELD_NOTES「踩坑流水」提炼回填。

## P1. flash-attn Linux wheel 与上游依赖声明冲突

- 症状：上游 `pyproject.toml` 声明的 flash-attn 在本机 CUDA/torch 组合下无预编译 wheel，安装卡源码编译数小时或失败。
- 检测：上游依赖含 `flash-attn` 且目标平台 Linux；比对本机 torch/CUDA 与可用 wheel（如 mjun0812/flash-attention-prebuild-wheels）。
- 绕法：安装期把依赖行替换为平台标记 + 预编译 wheel URL。现成实现：`mikazuki/engines/anima_fast/environment.py` `localize_linux_flash_attn_dependency`。
- 来源：anima_fast pack。

## P2. 可选/平台限定依赖把安装拖死

- 症状：上游声明的可选运行时依赖（掩膜/可视化/平台限定包）在目标平台装不上，整个 `uv pip install` 失败。
- 检测：安装日志失败包名不在训练链路 import 里。
- 绕法：安装前从依赖清单剥离，记日志「按需自装」。现成实现：anima_fast `environment.py` `strip_optional_runtime_dependencies`。
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

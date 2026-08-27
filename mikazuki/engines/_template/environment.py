"""environment.py stub — 环境安装与审计。

职责：uv python install 自己的解释器（不要共享 GUI 解释器底座，#251 已否决）、
uv venv + uv pip install 依赖、应用 patches/ 下的补丁、安装后 audit
（import torch + 引擎 import + CUDA 自检），结果写 install state。
输入：InstallPlan；输出：audit dict（ok/errors/facts）。
完成判据：audit 全绿 → state=ready；任一失败 → state=broken 且错误可读。
已知坑先扫 mikazuki/engines/KNOWN_PITFALLS.md。
参考：mikazuki/engines/anima_fast/environment.py。
"""

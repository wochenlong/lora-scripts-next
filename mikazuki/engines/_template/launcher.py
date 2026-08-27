"""launcher.py stub — 启动命令构造。

职责：build_launch_spec(runtime, script, args, task_id, gpu_ids) → LaunchSpec
(command/cwd/env)。env 处理：PYTHONNOUSERSITE=1、PYTHONUNBUFFERED=1、
剥离主项目 PYTHONPATH、按需注入 HF_HOME/CUDA_VISIBLE_DEVICES/引擎私有变量。
注意 Windows 中文环境的编码注入（见 KNOWN_PITFALLS.md）。
输入：RuntimeConfig + 训练参数；输出：LaunchSpec（mikazuki.process 消费）。
完成判据：构造的命令在隔离 venv 下可启动训练脚本。
参考：mikazuki/engines/musubi/launcher.py。
"""

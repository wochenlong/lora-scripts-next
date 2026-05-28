from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from .settings import RuntimeConfig


@dataclass
class LaunchSpec:
    command: list[str]
    cwd: Path
    env: dict[str, str]


def build_launch_spec(runtime: RuntimeConfig, config_path: Path, task_id: str, gpu_ids: list[str] | None = None) -> LaunchSpec:
    command = [
        str(runtime.python),
        str(runtime.anima_root / "train.py"),
        "--config_file",
        str(config_path.resolve()),
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["ACCELERATE_DISABLE_RICH"] = "1"
    env["ANIMA_FAST_PARENT_TASK_ID"] = task_id
    env.pop("PYTHONPATH", None)
    if runtime.hf_home is not None:
        env["HF_HOME"] = str(runtime.hf_home)
    if gpu_ids:
        env["CUDA_VISIBLE_DEVICES"] = ",".join(gpu_ids)
    return LaunchSpec(command=command, cwd=runtime.anima_root, env=env)

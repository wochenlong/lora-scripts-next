"""Build the isolated kogine launch specification."""
from dataclasses import dataclass
from pathlib import Path
import os

from .environment import process_env
from .settings import TRAIN_SCRIPT


@dataclass(frozen=True)
class LaunchSpec:
    command: list[str]
    cwd: Path
    env: dict[str, str]


def build_launch_spec(runtime, config_path, gpu_ids=None):
    env = process_env()
    if gpu_ids:
        env["CUDA_VISIBLE_DEVICES"] = ",".join(str(value) for value in gpu_ids)
    command = [
        str(runtime.kogine),
        "run",
        str(runtime.source / TRAIN_SCRIPT),
        "--config",
        str(config_path),
    ]
    return LaunchSpec(command=command, cwd=runtime.source, env=env)

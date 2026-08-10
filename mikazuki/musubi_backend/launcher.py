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


def _base_env(runtime: RuntimeConfig, task_id: str, gpu_ids: list[str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"
    env["TERM"] = "dumb"
    env["MUSUBI_PARENT_TASK_ID"] = task_id
    # The vendored source tree is the source of truth; root entry scripts are
    # thin wrappers that import the musubi_tuner package from src/.
    src = str((runtime.musubi_root / "src").resolve())
    existing = env.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if src not in parts:
        parts.insert(0, src)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    if runtime.hf_home is not None:
        env["HF_HOME"] = str(runtime.hf_home)
    if gpu_ids:
        env["CUDA_VISIBLE_DEVICES"] = ",".join(gpu_ids)
    return env


def build_cache_latents_spec(
    runtime: RuntimeConfig,
    dataset_toml: Path,
    vae: str,
    task_id: str,
    gpu_ids: list[str] | None = None,
    skip_existing: bool = True,
) -> LaunchSpec:
    command = [
        str(runtime.python),
        str(runtime.musubi_root / "krea2_cache_latents.py"),
        "--dataset_config",
        str(dataset_toml),
        "--vae",
        vae,
    ]
    if skip_existing:
        command.append("--skip_existing")
    return LaunchSpec(command=command, cwd=runtime.musubi_root, env=_base_env(runtime, task_id, gpu_ids))


def build_cache_text_encoder_spec(
    runtime: RuntimeConfig,
    dataset_toml: Path,
    text_encoder: str,
    task_id: str,
    gpu_ids: list[str] | None = None,
    skip_existing: bool = True,
) -> LaunchSpec:
    command = [
        str(runtime.python),
        str(runtime.musubi_root / "krea2_cache_text_encoder_outputs.py"),
        "--dataset_config",
        str(dataset_toml),
        "--text_encoder",
        text_encoder,
    ]
    if skip_existing:
        command.append("--skip_existing")
    return LaunchSpec(command=command, cwd=runtime.musubi_root, env=_base_env(runtime, task_id, gpu_ids))


def build_train_spec(
    runtime: RuntimeConfig,
    train_toml: Path,
    task_id: str,
    gpu_ids: list[str] | None = None,
) -> LaunchSpec:
    command = [
        str(runtime.python),
        str(runtime.musubi_root / "krea2_train_network.py"),
        "--config_file",
        str(train_toml),
    ]
    return LaunchSpec(command=command, cwd=runtime.musubi_root, env=_base_env(runtime, task_id, gpu_ids))

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 runtime
    import toml as tomllib  # type: ignore

from .settings import RuntimeConfig

_VALID_ACCELERATE_MIXED_PRECISION = {"no", "fp16", "bf16", "fp8"}


@dataclass
class LaunchSpec:
    command: list[str]
    cwd: Path
    env: dict[str, str]


def _normalize_mixed_precision(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized or normalized in {"none", "null"}:
        return None
    if normalized in _VALID_ACCELERATE_MIXED_PRECISION:
        return normalized
    return None


def _read_mixed_precision_from_train_toml(train_toml: Path) -> str | None:
    if not train_toml.is_file():
        return None
    try:
        data = tomllib.loads(train_toml.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not data:
        return None
    return _normalize_mixed_precision(data.get("mixed_precision"))


def _first_gpu_only(gpu_ids: list[str] | None) -> list[str] | None:
    """Cache stages stay single-process; pin to the first selected GPU."""
    if not gpu_ids:
        return None
    return [str(gpu_ids[0])]


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
        env["CUDA_VISIBLE_DEVICES"] = ",".join(str(g) for g in gpu_ids)
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
    return LaunchSpec(
        command=command,
        cwd=runtime.musubi_root,
        env=_base_env(runtime, task_id, _first_gpu_only(gpu_ids)),
    )


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
    return LaunchSpec(
        command=command,
        cwd=runtime.musubi_root,
        env=_base_env(runtime, task_id, _first_gpu_only(gpu_ids)),
    )


def build_train_spec(
    runtime: RuntimeConfig,
    train_toml: Path,
    task_id: str,
    gpu_ids: list[str] | None = None,
    *,
    cpu_threads: int = 1,
) -> LaunchSpec:
    """Build musubi Krea2 train argv via ``accelerate launch`` (multi-GPU capable).

    Upstream musubi-tuner documents ``accelerate launch … krea2_train_network.py``.
    We use the musubi venv's ``python -m accelerate.commands.launch`` so the
    correct Accelerate/Torch stack is used (not the Kohya/main env).
    """
    script = runtime.musubi_root / "krea2_train_network.py"
    launch_opts = [
        "--num_cpu_threads_per_process",
        str(cpu_threads),
        "--quiet",
    ]
    mixed_precision = _read_mixed_precision_from_train_toml(train_toml)
    if mixed_precision:
        launch_opts.extend(["--mixed_precision", mixed_precision])

    multi_gpu_args: list[str] = []
    env = _base_env(runtime, task_id, gpu_ids)
    env["ACCELERATE_DISABLE_RICH"] = "1"

    if gpu_ids and len(gpu_ids) > 1:
        multi_gpu_args = ["--multi_gpu", "--num_processes", str(len(gpu_ids))]
        if sys.platform == "win32":
            env["USE_LIBUV"] = "0"
            multi_gpu_args = ["--rdzv_backend", "c10d", *multi_gpu_args]

    command = [
        str(runtime.python),
        "-m",
        "accelerate.commands.launch",
        *multi_gpu_args,
        *launch_opts,
        str(script),
        "--config_file",
        str(train_toml),
    ]
    return LaunchSpec(command=command, cwd=runtime.musubi_root, env=env)

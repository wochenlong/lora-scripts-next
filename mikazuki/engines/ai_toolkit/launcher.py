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


def build_train_spec(
    runtime: RuntimeConfig,
    config_yaml: Path,
    task_id: str,
    gpu_ids: list[str] | None = None,
) -> LaunchSpec:
    """Single-stage launch: ai-toolkit's run.py drives cache/train/sample
    internally off one YAML config."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"
    env["TERM"] = "dumb"
    env["AI_TOOLKIT_PARENT_TASK_ID"] = task_id
    # run.py enables hf-xet by default; the xet CAS backend 401s behind
    # proxies/mirrors. Fall back to plain CDN download unless the user opted in.
    env.setdefault("HF_HUB_DISABLE_XET", "1")
    # run.py does sys.path.insert(0, os.getcwd()); keep cwd at the source root
    # and mirror it in PYTHONPATH for child processes.
    src = str(runtime.toolkit_root.resolve())
    existing = env.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if src not in parts:
        parts.insert(0, src)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    if runtime.hf_home is not None:
        env["HF_HOME"] = str(runtime.hf_home)
    if gpu_ids:
        env["CUDA_VISIBLE_DEVICES"] = ",".join(str(g) for g in gpu_ids)

    command = [str(runtime.python), "run.py", str(config_yaml)]
    return LaunchSpec(command=command, cwd=runtime.toolkit_root, env=env)

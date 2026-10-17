"""Single-GPU MOSS cache -> train task, launched only by the shared task queue."""
from dataclasses import dataclass
from pathlib import Path

from .adapter import argv_for
from .environment import process_env


@dataclass
class LaunchSpec:
    command: list[str]
    cwd: Path
    env: dict[str, str]


def pipeline_commands(runtime, adapted):
    commands = []
    if adapted.run_preprocess:
        commands.append([str(runtime.python), "-E", "-s", "-u", "-X", "utf8", "-m", "scripts.moss.cache", *argv_for(adapted.cache)])
    commands.append([str(runtime.python), "-E", "-s", "-u", "-X", "utf8", "-m", "scripts.moss.train", *argv_for(adapted.train)])
    return commands


def build_train_spec(runtime, config_path, gpu_ids=None):
    if gpu_ids is not None and not isinstance(gpu_ids, list):
        raise ValueError("gpu_ids: expected a list / 必须为列表")
    if gpu_ids and (len(gpu_ids) > 1 or any(not str(gpu).isdigit() for gpu in gpu_ids)):
        raise ValueError("MOSS supports one GPU / MOSS 仅支持单卡，请选择一张 GPU")
    # The queue restores tasks by merging today's host environment. Interpreter
    # flags keep PYTHONPATH/PYTHONHOME isolated even after a server restart.
    command = [str(runtime.python), "-E", "-s", "-u", "-X", "utf8", str(Path(__file__).with_name("entry.py").resolve()),
               "--project-root", str(runtime.project_root), "--config", str(config_path)]
    env = process_env()
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_XET="1",
               TOKENIZERS_PARALLELISM="false", ANIMA_HOME=str(runtime.source))
    if gpu_ids:
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_ids[0])
    return LaunchSpec(command, runtime.source, env)

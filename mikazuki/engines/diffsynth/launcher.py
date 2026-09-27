from dataclasses import dataclass
from pathlib import Path

from .environment import process_env


@dataclass
class LaunchSpec:
    command: list[str]
    cwd: Path
    env: dict[str, str]


def build_train_spec(runtime, config_path, gpu_ids=None):
    if gpu_ids and len(gpu_ids) > 1:
        raise ValueError("当前 DiffSynth 适配仅支持单卡训练，请选择一张 GPU。")
    # GPU selection is carried by CUDA_VISIBLE_DEVICES below. Do not let a
    # user-wide Accelerate gpu_ids value (e.g. "no") replace that selection.
    command = [str(runtime.python), "-m", "accelerate.commands.launch", "--num_processes", "1", "--num_machines", "1", "--gpu_ids", "all", "--mixed_precision", "bf16", "--dynamo_backend", "no", str(Path(__file__).with_name("entry.py").resolve()), "--project-root", str(runtime.project_root), "--config", str(config_path)]
    env = process_env()
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_XET="1", TOKENIZERS_PARALLELISM="false")
    if gpu_ids:
        env["CUDA_VISIBLE_DEVICES"] = ",".join(str(gpu) for gpu in gpu_ids)
    return LaunchSpec(command, runtime.source, env)

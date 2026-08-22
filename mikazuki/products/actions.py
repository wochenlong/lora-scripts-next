"""Product actions (resize / merge / extract) — lightweight compute tasks.

Actions are executed through TaskManager on the compute lane (queued while
training runs), always using the ``scripts/dev/networks`` copies (decision:
no stable/dev dispatch). The user picks the output path; the output
directory is registered as a scan dir and the would-be product id gets a
``derived_from`` lineage record, so the new product shows lineage as soon
as it is scanned.
"""

import os
import subprocess
from pathlib import Path
from typing import List, Optional

from mikazuki.launch_utils import base_dir_path, python_bin
from mikazuki.products.registry import Registry, product_id_for_path
from mikazuki.tasks import tm
from mikazuki.utils.train_utils import read_safetensors_metadata

SCRIPTS_SUBDIR = Path("scripts") / "dev"
NETWORKS_DIR = SCRIPTS_SUBDIR / "networks"


class ActionError(ValueError):
    pass


_CUDA_AVAILABLE: Optional[bool] = None


def cuda_available() -> bool:
    """Probe CUDA once with the action interpreter; the shell process itself
    stays torch-free, so detection happens in a subprocess and is cached."""
    global _CUDA_AVAILABLE
    if _CUDA_AVAILABLE is None:
        try:
            result = subprocess.run(
                [str(python_bin), "-c", "import torch; print(torch.cuda.is_available())"],
                capture_output=True, text=True, timeout=180,
            )
            _CUDA_AVAILABLE = result.returncode == 0 and result.stdout.strip() == "True"
        except Exception:  # noqa: BLE001
            _CUDA_AVAILABLE = False
    return _CUDA_AVAILABLE


def scripts_root() -> Path:
    root = Path(base_dir_path()) / SCRIPTS_SUBDIR
    if not root.is_dir():
        raise ActionError(f"动作脚本目录不存在: {root}")
    return root


def _build_env() -> dict:
    env = os.environ.copy()
    scripts_dir = str(scripts_root())
    existing = env.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if scripts_dir not in parts:
        parts.insert(0, scripts_dir)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _submit(registry: Registry, *, action: str, script: str, args: List[str],
            output_path: str, derived_from: List[str], extra_meta: Optional[dict] = None) -> dict:
    output = Path(output_path)
    if not output.parent.is_dir():
        raise ActionError(f"输出目录不存在: {output.parent}")

    command = [str(python_bin), str(Path("networks") / script), *args]
    metadata = {
        "job_label": f"制品动作 {action}",
        "kind": f"product_{action}",
        "action": action,
        "output_path": str(output),
        "derived_from": derived_from,
    }
    metadata.update(extra_meta or {})

    task = tm.create_task(command, _build_env(), metadata=metadata, cwd=str(scripts_root()))
    queued = task.status.name == "QUEUED"
    tm.submit(task)

    # Lineage without path: no "missing" row before the file exists; the
    # scanner merges derived_from once the output is scanned.
    registry.update_product_state(product_id_for_path(output), derived_from=derived_from)
    registry.add_scan_dir(output.parent)

    return {"task_id": task.task_id, "queued": queued}


def check_resizable(product_path: str) -> None:
    """Raise ActionError unless the file is a kohya-format LoRA (lora_down/up)."""
    header = read_safetensors_metadata(product_path) or {}
    metadata = header.get("__metadata__", {}) if isinstance(header, dict) else {}
    module = str(metadata.get("ss_network_module") or "").lower()
    if "lycoris" in module or "lokr" in module or "loha" in module:
        raise ActionError("LoKr/LoHA 等 LyCORIS 格式是 Kronecker 分解，没有 lora_down/up，无法 resize")
    keys = [k for k in header.keys() if k != "__metadata__"] if isinstance(header, dict) else []
    if keys and not any("lora_down" in k or "lora_A" in k for k in keys):
        raise ActionError("未找到 lora_down/lora_up 权重键，不是标准 LoRA，无法 resize")


def build_resize_args(source: str, output_path: str, *, new_rank=None,
                      new_conv_rank=None, dynamic_method=None, dynamic_param=None,
                      save_precision=None) -> List[str]:
    args = ["--model", source, "--save_to", output_path]
    if dynamic_method:
        args += ["--dynamic_method", dynamic_method, "--dynamic_param", str(dynamic_param)]
    if new_rank is not None:
        args += ["--new_rank", str(new_rank)]
    if new_conv_rank is not None:
        args += ["--new_conv_rank", str(new_conv_rank)]
    if save_precision:
        args += ["--save_precision", save_precision]
    return args


def submit_resize(registry: Registry, *, source: str, output_path: str,
                  new_rank: Optional[int] = None, new_conv_rank: Optional[int] = None,
                  dynamic_method: Optional[str] = None, dynamic_param: Optional[float] = None,
                  save_precision: Optional[str] = None) -> dict:
    if not Path(source).is_file():
        raise ActionError(f"制品文件不存在: {source}")
    if dynamic_method:
        if dynamic_param is None:
            raise ActionError("dynamic 模式需要 dynamic_param")
    elif new_rank is None:
        raise ActionError("需要目标 dim（new_rank）或 dynamic 保留率")
    check_resizable(source)

    args = build_resize_args(source, output_path, new_rank=new_rank,
                             new_conv_rank=new_conv_rank, dynamic_method=dynamic_method,
                             dynamic_param=dynamic_param, save_precision=save_precision)
    if cuda_available():
        # resize_lora.py defaults to CPU when --device is omitted; per-layer SVD
        # on CPU takes hours for SDXL-sized LoRAs.
        args += ["--device", "cuda"]

    return _submit(registry, action="resize", script="resize_lora.py", args=args,
                   output_path=output_path, derived_from=[product_id_for_path(source)])


def build_merge_args(sources: List[str], ratios: List[float], output_path: str, *,
                     concat=False, shuffle=False, precision="float",
                     save_precision="float") -> List[str]:
    args = ["--save_to", output_path, "--precision", precision, "--save_precision", save_precision]
    args += ["--models", *sources]
    args += ["--ratios", *[str(r) for r in ratios]]
    if concat:
        args.append("--concat")
    if shuffle:
        args.append("--shuffle")
    return args


def submit_merge(registry: Registry, *, sources: List[str], ratios: List[float],
                 output_path: str, concat: bool = False, shuffle: bool = False,
                 precision: str = "float", save_precision: str = "float") -> dict:
    if len(sources) < 2:
        raise ActionError("merge 至少需要两个制品")
    for src in sources:
        if not Path(src).is_file():
            raise ActionError(f"制品文件不存在: {src}")
    if len(ratios) != len(sources):
        raise ActionError("ratios 数量必须与制品数量一致")

    args = build_merge_args(sources, ratios, output_path, concat=concat,
                            shuffle=shuffle, precision=precision, save_precision=save_precision)

    return _submit(registry, action="merge", script="merge_lora.py", args=args,
                   output_path=output_path,
                   derived_from=[product_id_for_path(s) for s in sources])


def submit_extract(registry: Registry, *, model_org: str, model_tuned: str,
                   output_path: str, dim: int, conv_dim: Optional[int] = None,
                   sdxl: bool = False, v2: bool = False) -> dict:
    for label, p in (("底模", model_org), ("微调模型", model_tuned)):
        if not Path(p).is_file():
            raise ActionError(f"{label}文件不存在: {p}")

    args = ["--model_org", model_org, "--model_tuned", model_tuned,
            "--save_to", output_path, "--dim", str(dim)]
    if conv_dim is not None:
        args += ["--conv_dim", str(conv_dim)]
    if sdxl:
        args.append("--sdxl")
    if v2:
        args.append("--v2")

    return _submit(registry, action="extract", script="extract_lora_from_models.py", args=args,
                   output_path=output_path, derived_from=[product_id_for_path(model_tuned)])

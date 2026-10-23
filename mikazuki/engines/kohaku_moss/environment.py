"""Independent Python 3.12 runtime and dependency audit."""
from __future__ import annotations

import json
import os
import subprocess

from mikazuki.download_sources import install_process_env, pytorch_extra_index_url

from .manifest import UPSTREAM
from .settings import PYTHON_VERSION, TRAIN_SCRIPT

TORCH_REQUIREMENTS = ("torch>=2.13,<2.15", "torchvision")
LYCORIS_REQUIREMENT = "lycoris-lora>=4.1.2"


def process_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "UV_PYTHON"):
        env.pop(name, None)
    env.update(PYTHONNOUSERSITE="1", PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    return env


def install_env(runtime, sources=None) -> dict[str, str]:
    env = process_env()
    if sources is not None:
        env.update(install_process_env(sources))
    env["UV_PYTHON_INSTALL_DIR"] = str(runtime.python_install_dir)
    return env


def install_commands(runtime, sources) -> list[list[str]]:
    torch_index = pytorch_extra_index_url(
        sources.pytorch_index_url, "cu130", "https://download.pytorch.org/whl/cu130"
    )
    index = ["--index-url", sources.pip_index_url] if sources.pip_index_url else []
    pip = ["uv", "pip", "install", "--python", str(runtime.python)]
    return [
        ["uv", "python", "install", PYTHON_VERSION, "--install-dir", str(runtime.python_install_dir)],
        ["uv", "venv", "--clear", "--managed-python", "--python", PYTHON_VERSION, str(runtime.root / ".venv")],
        [*pip, "--index-url", torch_index, *TORCH_REQUIREMENTS],
        [
            *pip,
            *index,
            "--extra-index-url",
            torch_index,
            "--index-strategy",
            "unsafe-best-match",
            "-e",
            f"{runtime.source}[cuda,optim]",
            LYCORIS_REQUIREMENT,
            *TORCH_REQUIREMENTS,
        ],
    ]


def audit_environment(runtime, *, runner=None) -> dict:
    run = runner or subprocess.run
    errors: list[str] = []
    facts: dict = {}
    required = (runtime.python, runtime.kogine, runtime.source / TRAIN_SCRIPT, runtime.source / "pyproject.toml")
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return {"ok": False, "errors": ["KohakuMossTrainer 环境缺少：" + ", ".join(missing)], "facts": facts}
    fallback_file = runtime.source / "src" / "kohakumoss_kernels" / "errors.py"
    fallback_ready = fallback_file.is_file() and "subprocess.CalledProcessError" in fallback_file.read_text(encoding="utf-8")
    facts["windows_build_fallback"] = fallback_ready
    if not fallback_ready:
        errors.append("KohakuMossTrainer 缺少 Windows Triton 编译失败回退补丁。")
    probe = """
import importlib.metadata as md, json, torch
import kohakumoss, kohakuengine, lycoris, prodigyopt, schedulefree
print(json.dumps({"torch": torch.__version__, "cuda": torch.version.cuda,
 "cuda_available": torch.cuda.is_available(), "lycoris": md.version("lycoris-lora"),
 "kohakumoss": md.version("kohakumoss")}))
"""
    kwargs = {"cwd": runtime.source, "env": process_env(), "capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"}
    head = run(["git", "-C", str(runtime.source), "rev-parse", "HEAD"], **kwargs)
    facts["source_commit"] = head.stdout.strip()
    if head.returncode or facts["source_commit"] != UPSTREAM["commit"]:
        errors.append("KohakuMossTrainer 源码版本与钉版提交不一致。")
    result = run([str(runtime.python), "-c", probe], **kwargs)
    if result.returncode:
        errors.append("依赖导入审计失败：" + (result.stderr or result.stdout)[-4000:].strip())
    else:
        facts.update(json.loads(result.stdout.strip().splitlines()[-1]))
        if not facts.get("cuda_available"):
            errors.append("未检测到 CUDA GPU；KohakuMossTrainer 当前集成仅支持 NVIDIA CUDA。")
    return {"ok": not errors, "errors": errors, "warnings": [], "facts": facts}

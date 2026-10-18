"""Explicit MOSS dependency closure; never import ML packages in the GUI.

Versions follow the pinned upstream lock's default CUDA stack. Upstream's full
project also installs SAM, GUI, Comfy, and curation applications, so do not run
uv sync or install its dependencies wholesale. The source and anime-tools
(required by the torch-free weight catalog) are installed with --no-deps.
MOSS uses PyTorch SDPA, not flash-attn; no optional CUDA extension is compiled.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys

from mikazuki.download_sources import apply_github_prefix, install_process_env, pytorch_extra_index_url
from .manifest import UPSTREAM
from .settings import PYTHON_VERSION, REQUIRED_SOURCE_FILES

TORCH_PINS = ("torch==2.14.1+cu132", "torchvision==0.29.1+cu132")
DIFFUSERS_COMMIT = "80c7ed262aeffbeb43ef13ae04baeb9b84515a69"
ANIME_TOOLS_COMMIT = "53af580c84fab07372e852b04a6f1880d2ebab4d"
CORE_DEPENDENCIES = (
    "transformers==5.16.1", "accelerate==1.13.0", "safetensors==0.8.0",
    "numpy==2.4.4", "Pillow==12.2.0", "sentencepiece>=0.2.1",
    "huggingface-hub>=1.9.0", "einops>=0.7.0", "tensorboard", "psutil", "rich", "tqdm",
)
EXPECTED_VERSIONS = {
    "torch": "2.14.1+cu132", "torchvision": "0.29.1+cu132",
    "transformers": "5.16.1", "diffusers": "0.41.0.dev0",
    "accelerate": "1.13.0", "safetensors": "0.8.0", "anime-tools": "0.7.12",
}


def supported_platform():
    machine = platform.machine().lower()
    if sys.platform.startswith("linux") and machine in {"x86_64", "amd64", "aarch64", "arm64"}:
        return
    if sys.platform == "win32" and machine in {"x86_64", "amd64"}:
        return
    raise ValueError("MOSS CUDA 环境支持 Linux x86_64/aarch64 和 Windows x86_64。")


def process_env():
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "UV_PYTHON", "UV_PYTHON_PREFERENCE"):
        env.pop(name, None)
    env.update(PYTHONNOUSERSITE="1", PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    return env


def install_env(runtime, sources=None):
    env = process_env()
    env.update(install_process_env(sources))
    # A host PYTHONPATH/venv must not leak back through a network-policy env.
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "UV_PYTHON", "UV_PYTHON_PREFERENCE"):
        env.pop(name, None)
    env.update(UV_PYTHON_INSTALL_DIR=str(runtime.python_install_dir))
    return env


def install_commands(runtime, sources):
    supported_platform()
    index = sources.pip_index_url or "https://pypi.org/simple"
    torch_index = pytorch_extra_index_url(sources.pytorch_index_url, "cu132", "https://download.pytorch.org/whl/cu132")
    pip = ["uv", "pip", "install", "--no-config", "--python", str(runtime.python), "--index-url", index]
    git_target = lambda repo, commit: "git+" + apply_github_prefix(f"https://github.com/{repo}.git", sources.github_url_prefix) + "@" + commit
    dependencies = [*CORE_DEPENDENCIES, "diffusers @ " + git_target("huggingface/diffusers", DIFFUSERS_COMMIT)]
    if sys.platform == "win32":
        dependencies.append("triton-windows==3.8.0.post29")
    return [
        ["uv", "python", "install", PYTHON_VERSION, "--install-dir", str(runtime.python_install_dir)],
        ["uv", "venv", "--clear", "--managed-python", "--python", PYTHON_VERSION, str(runtime.root / ".venv")],
        [*pip, "--extra-index-url", torch_index, "--index-strategy", "unsafe-best-match", *TORCH_PINS, *dependencies],
        [*pip, "--no-deps", "anime-tools @ " + git_target("sorryhyun/anime_tools", ANIME_TOOLS_COMMIT)],
        [*pip, "--no-deps", "-e", str(runtime.source)],
    ]


IMPORT_PROBE = """
import json, sys, importlib.metadata as md
from library.moss.requests import CacheRequest, TrainRequest
assert CacheRequest.from_argv(CacheRequest().to_argv()) == CacheRequest()
assert TrainRequest.from_argv(TrainRequest().to_argv()) == TrainRequest()
import torch, torchvision, accelerate, safetensors, numpy, PIL
from transformers import AutoModel, AutoTokenizer, Qwen3_5Config
from diffusers import AutoencoderKLFlux2
from torch.utils.tensorboard import SummaryWriter
from library.moss.cache import run_cache
from library.moss.train import run_train
from library.qwen21.blockswap import ModelOffloader
from scripts.moss.cache import main as cache_main
from scripts.moss.train import main as train_main
packages = %s
print(json.dumps({'python_version': '.'.join(map(str, sys.version_info[:3])),
    'base_prefix': sys.base_prefix, 'prefix': sys.prefix,
    'versions': {name: md.version(name) for name in packages},
    'cuda': torch.version.cuda, 'cuda_available': torch.cuda.is_available(),
    'bf16_supported': torch.cuda.is_available() and torch.cuda.is_bf16_supported()}))
""" % repr(list(EXPECTED_VERSIONS))


def audit_environment(runtime, *, runner=None):
    """Import real MOSS entry points without loading models or starting jobs."""
    run = runner or subprocess.run
    errors = []
    facts = {}
    if not runtime.python.is_file():
        errors.append(f"独立 Python 缺失：{runtime.python}")
    errors.extend(f"MOSS 源码缺失：{name}" for name in REQUIRED_SOURCE_FILES if not (runtime.source / name).is_file())
    if errors:
        return {"ok": False, "errors": errors, "warnings": [], "facts": facts}
    try:
        kwargs = dict(cwd=runtime.source, env=process_env(), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        head = run(["git", "-C", str(runtime.source), "rev-parse", "HEAD"], **kwargs)
        facts["source_commit"] = head.stdout.strip()
        if head.returncode or facts["source_commit"] != UPSTREAM["commit"]:
            errors.append("MOSS 源码版本与钉版提交不一致，请修复环境。")
        from .source_integrity import verify_source
        try:
            facts.update(verify_source(runtime))
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            errors.append(str(exc))
        if not errors:
            env = process_env()
            env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_XET="1")
            probe = run([str(runtime.python), "-c", IMPORT_PROBE], **{**kwargs, "env": env})
            if probe.returncode:
                errors.append("MOSS 依赖/入口审计失败：" + (probe.stderr or probe.stdout or "无输出")[-6000:].strip())
            else:
                facts.update(json.loads(probe.stdout.strip().splitlines()[-1]))
                if not facts.get("python_version", "").startswith("3.13."):
                    errors.append("MOSS 要求独立 Python 3.13。")
                from pathlib import Path
                if not Path(facts.get("base_prefix", "")).resolve().is_relative_to(runtime.python_install_dir.resolve()):
                    errors.append("MOSS venv 未使用本扩展管理的独立 Python。")
                if Path(facts.get("prefix", "")).resolve() != (runtime.root / ".venv").resolve():
                    errors.append("MOSS 依赖审计未运行在本扩展的 venv。")
                for name, expected in EXPECTED_VERSIONS.items():
                    if facts.get("versions", {}).get(name) != expected:
                        errors.append(f"MOSS 依赖版本不匹配：{name}，需要 {expected}。")
                if facts.get("cuda") != "13.2" or not facts.get("cuda_available"):
                    errors.append("MOSS CUDA 13.2 运行时未检测到可用 GPU，请检查 NVIDIA 驱动和 GPU。")
                if not facts.get("bf16_supported"):
                    errors.append("MOSS 需要支持 BF16 的 CUDA GPU。")
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError, TypeError) as exc:
        errors.append(f"MOSS 环境审计失败：{exc}")
    return {"ok": not errors, "errors": errors, "warnings": [], "facts": facts}

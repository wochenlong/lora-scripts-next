"""An independent uv-managed interpreter and venv; no GUI torch imports.

Dependency pins mirror the training subset of the historical shared
``requirements.txt`` so training behavior matches the pre-split environment.
"""
import json
import os
import platform
import subprocess
import sys

from .settings import PYTHON_VERSION
from mikazuki.download_sources import pytorch_extra_index_url

# cu128 wheels exist for Windows and Linux x86_64 only; Linux aarch64 falls
# back to the pip index (PyPI ships CUDA-capable aarch64 wheels), see #385.
TORCH_PINS = ["torch==2.7.0+cu128", "torchvision==0.22.0+cu128"]
TORCH_PINS_AARCH64 = ["torch==2.13.0", "torchvision==0.28.0"]
# Requirement specifiers satisfied by the already-installed local-version
# wheels (PEP 440 ignores the local segment when the specifier has none).
TORCH_REQUIREMENTS = ["torch==2.7.0", "torchvision==0.22.0"]
TORCH_REQUIREMENTS_AARCH64 = TORCH_PINS_AARCH64
XFORMERS_PIN = "xformers==0.0.30"

TRAINING_DEPS = [
    "accelerate==0.33.0",
    "transformers==4.51.3",
    "diffusers[torch]==0.33.1",
    "ftfy==6.1.1",
    "opencv-python==4.8.1.78",
    # flow_use_ot in sd-scripts uses scipy.optimize.linear_sum_assignment.
    "scipy",
    "einops==0.7.0",
    "pytorch-lightning==1.9.0",
    # CUDA 13 torch needs bitsandbytes>=0.48 binaries; the floor is 0.46.0.
    "bitsandbytes>=0.46.0",
    "lion-pytorch==0.1.2",
    "schedulefree==1.4",
    "pytorch-optimizer==3.7.0",
    "prodigy-plus-schedule-free==1.9.0",
    "prodigyopt==1.1.2",
    "tensorboard==2.14.0",
    "safetensors==0.4.4",
    "setuptools<81",
    "altair==4.2.2",
    "easygui==0.98.3",
    "toml==0.10.2",
    "voluptuous==0.13.1",
    "huggingface-hub==0.36.2",
    "imagesize==1.4.1",
    "sentencepiece==0.2.0",
    "protobuf==3.20.3",
    "rich==13.7.0",
    "open-clip-torch==2.20.0",
    "lycoris-lora==3.3.0",
    "dadaptation==3.1",
    "modelscope>=1.20.0",
    "optimum-quanto",
    "wandb==0.16.2",
    "numpy==1.26.4",
    "pillow",
    'triton-windows<3.4; sys_platform == "win32"',
]


def _linux_aarch64():
    return sys.platform.startswith("linux") and platform.machine() in {"aarch64", "arm64"}


def _torch_index_args(sources):
    if _linux_aarch64():
        return ["--index-url", sources.pip_index_url] if sources.pip_index_url else []
    torch_index = pytorch_extra_index_url(sources.pytorch_index_url, "cu128", "https://download.pytorch.org/whl/cu128")
    return ["--index-url", torch_index]


def _torch_pins():
    return TORCH_PINS_AARCH64 if _linux_aarch64() else TORCH_PINS


def _torch_requirements():
    return TORCH_REQUIREMENTS_AARCH64 if _linux_aarch64() else TORCH_REQUIREMENTS


def install_commands(runtime, sources):
    index = ["--index-url", sources.pip_index_url] if sources.pip_index_url else []
    commands = [
        ["uv", "python", "install", PYTHON_VERSION, "--install-dir", str(runtime.python_install_dir)],
        ["uv", "venv", "--clear", "--managed-python", "--python", PYTHON_VERSION, str(runtime.root / ".venv")],
        ["uv", "pip", "install", "--python", str(runtime.python), *_torch_index_args(sources), *_torch_pins()],
    ]
    if not _linux_aarch64():
        commands.append(["uv", "pip", "install", "--python", str(runtime.python), *_torch_index_args(sources), "--no-deps", XFORMERS_PIN])
    commands.append(["uv", "pip", "install", "--python", str(runtime.python), *index, *TRAINING_DEPS, *_torch_requirements()])
    return commands


def process_env():
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(PYTHONNOUSERSITE="1", PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    return env


def install_env(runtime):
    env = process_env()
    env["UV_PYTHON_INSTALL_DIR"] = str(runtime.python_install_dir)
    return env


def audit_environment(runtime):
    code = (
        "import json, torch, accelerate, transformers, diffusers, scipy; "
        "import lycoris, open_clip; "
        "print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.is_available()}))"
    )
    result = subprocess.run([str(runtime.python), "-c", code], env=process_env(), text=True, encoding="utf-8", capture_output=True)
    if result.returncode:
        return {"ok": False, "errors": [result.stderr.strip()]}
    facts = json.loads(result.stdout.strip().splitlines()[-1])
    errors = []
    if not facts["gpu"]:
        errors.append("未检测到 CUDA GPU，不能启动训练。")
    return {"ok": not errors, "errors": errors, **facts}

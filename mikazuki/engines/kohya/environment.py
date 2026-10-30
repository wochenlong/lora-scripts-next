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
    # Qwen3.5 needs Transformers 5.x, while the existing SD trainers require
    # CLIPTextModel's text_model wrapper removed by later 5.x releases.
    # Keep this verified pair together for both model families.
    "accelerate==1.15.0",
    "transformers==5.5.3",
    "diffusers[torch]==0.40.0",
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
    "safetensors==0.8.0",
    "setuptools<81",
    "altair==4.2.2",
    "easygui==0.98.3",
    "toml==0.10.2",
    "voluptuous==0.13.1",
    "huggingface-hub==1.32.0",
    "tokenizers==0.22.2",
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


def pinned_requirements():
    """The pinned training stack as parsed requirements (markers evaluated)."""
    from packaging.requirements import Requirement

    reqs = []
    for spec in [*TRAINING_DEPS, *_torch_requirements()]:
        req = Requirement(spec)
        if req.marker and not req.marker.evaluate():
            continue
        reqs.append(req)
    if not _linux_aarch64():
        reqs.append(Requirement(XFORMERS_PIN))
    return reqs


def compute_drift(installed_versions):
    """Compare installed versions against the pinned stack.

    Returns a list of {name, spec, installed} entries for packages that are
    missing or violate their pin; empty means the env matches the pins.
    """
    from packaging.utils import canonicalize_name

    installed_normalized = {canonicalize_name(name): version for name, version in installed_versions.items()}
    drift = []
    for req in pinned_requirements():
        installed = installed_normalized.get(canonicalize_name(req.name))
        if installed is None:
            drift.append({"name": req.name, "spec": str(req.specifier) or "*", "installed": None})
        elif req.specifier and not req.specifier.contains(installed, prereleases=True):
            drift.append({"name": req.name, "spec": str(req.specifier), "installed": installed})
    return drift


def upgrade_commands(runtime, sources, drift):
    """Incremental per-pin upgrade for the standalone venv — never recreates
    the venv and never touches packages that still satisfy their pin."""
    if not drift:
        return []
    torch_names = {"torch", "torchvision", "xformers"}
    torch_specs = [f"{d['name']}{d['spec']}" for d in drift if d["name"].lower() in torch_names]
    other_specs = [f"{d['name']}{d['spec']}" for d in drift if d["name"].lower() not in torch_names]
    index = ["--index-url", sources.pip_index_url] if sources.pip_index_url else []
    commands = []
    if torch_specs:
        commands.append(["uv", "pip", "install", "--python", str(runtime.python), *_torch_index_args(sources), *torch_specs])
    if other_specs:
        commands.append(["uv", "pip", "install", "--python", str(runtime.python), *index, *other_specs])
    return commands


def main_env_upgrade_commands(python, sources, drift):
    """Incremental per-pin upgrade for a legacy main environment (pip)."""
    if not drift:
        return []
    specs = [f"{d['name']}{d['spec']}" for d in drift]
    index = ["--index-url", sources.pip_index_url] if sources.pip_index_url else []
    return [[str(python), "-m", "pip", "install", *index, *specs]]


def process_env():
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(PYTHONNOUSERSITE="1", PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    return env


def install_env(runtime):
    from mikazuki.engines.portable_venv import ensure_uv_on_path
    env = ensure_uv_on_path(process_env())
    env["UV_PYTHON_INSTALL_DIR"] = str(runtime.python_install_dir)
    return env


# MOSS-Image trains on the Qwen3.5 text encoder, which only exists in
# transformers 5.x; older environments (e.g. legacy main envs) stay usable for
# the other train types but must not start a MOSS run.
MOSS_MIN_TRANSFORMERS_MAJOR = 5


def moss_stack_error(audit_facts):
    facts = audit_facts or {}
    if "qwen35" in facts:
        if facts["qwen35"]:
            return None
    else:
        version = str(facts.get("transformers") or "")
        try:
            major = int(version.split(".")[0])
        except (ValueError, IndexError):
            major = 0
        if major >= MOSS_MIN_TRANSFORMERS_MAJOR:
            return None
    return "MOSS-Image 需要 transformers 5.x（Qwen3.5 文本编码器）；当前训练环境版本过旧，请到训练引擎管理中安装/修复 kohya 独立环境。"


def audit_python(python, allow_user_site=False):
    code = (
        "import json, torch, accelerate, transformers, diffusers, scipy; "
        "import lycoris, open_clip, tokenizers; "
        "import importlib.metadata as im; "
        "vs={}; [vs.__setitem__(n, d.version) for d in im.distributions() if (n := d.metadata.get('Name'))]; "
        "print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.is_available(),"
        "'transformers':transformers.__version__,'tokenizers':tokenizers.__version__,'versions':vs,"
        "'qwen35':hasattr(transformers,'Qwen3_5TextConfig')}))"
    )
    env = process_env()
    if allow_user_site:
        # Training launchers honor pip --user installs on the main
        # environment; the fallback audit must see the same packages.
        env.pop("PYTHONNOUSERSITE", None)
    try:
        result = subprocess.run([str(python), "-c", code], env=env, text=True, encoding="utf-8", capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "errors": [f"审计子进程无法执行或超时: {exc}"]}
    if result.returncode:
        return {"ok": False, "errors": [result.stderr.strip()]}
    facts = json.loads(result.stdout.strip().splitlines()[-1])
    errors = []
    if not facts["gpu"]:
        errors.append("未检测到 CUDA GPU，不能启动训练。")
    return {"ok": not errors, "errors": errors, **facts}


def audit_environment(runtime):
    return audit_python(runtime.python)

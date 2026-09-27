"""An independent uv-managed interpreter and venv; no GUI torch imports."""
import json
import os
import subprocess

from .settings import PYTHON_VERSION, TRAIN_SCRIPT
from mikazuki.download_sources import pytorch_extra_index_url


def install_commands(runtime, sources):
    index = ["--index-url", sources.pip_index_url] if sources.pip_index_url else []
    torch_index = pytorch_extra_index_url(sources.pytorch_index_url, "cu128", "https://download.pytorch.org/whl/cu128")
    return [
        ["uv", "python", "install", PYTHON_VERSION, "--install-dir", str(runtime.python_install_dir)],
        ["uv", "venv", "--clear", "--managed-python", "--python", PYTHON_VERSION, str(runtime.root / ".venv")],
        ["uv", "pip", "install", "--python", str(runtime.python), "--index-url", torch_index, "torch==2.8.0", "torchvision==0.23.0"],
        ["uv", "pip", "install", "--python", str(runtime.python), *index, "-e", str(runtime.source), "transformers>=4.57.1,<5", "tensorboard", "bitsandbytes==0.48.2", "opencv-python-headless==4.11.0.86", "torch==2.8.0", "torchvision==0.23.0"],
    ]


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
        "import json, torch, diffsynth, accelerate, peft; "
        "from transformers import Qwen3VLConfig, Qwen3VLForConditionalGeneration; "
        "from torch.utils.tensorboard import SummaryWriter; "
        "from diffsynth.pipelines.qwen_image_21 import QwenImage21Pipeline; "
        "print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.is_available()}))"
    )
    result = subprocess.run([str(runtime.python), "-c", code], cwd=runtime.source, env=process_env(), text=True, encoding="utf-8", capture_output=True)
    if result.returncode:
        return {"ok": False, "errors": [result.stderr.strip()]}
    facts = json.loads(result.stdout.strip().splitlines()[-1])
    # --help imports the exact training entry without loading model weights.
    entry = subprocess.run([str(runtime.python), str(runtime.source / TRAIN_SCRIPT), "--help"], cwd=runtime.source, env=process_env(), text=True, encoding="utf-8", capture_output=True)
    errors = [] if entry.returncode == 0 else [entry.stderr.strip()]
    if not facts["gpu"]:
        errors.append("未检测到 CUDA GPU，不能启动训练。")
    return {"ok": not errors, "errors": errors, **facts}

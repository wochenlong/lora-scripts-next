"""从已发布源码中提取纯配方；不导入旧安装器及其 GUI 依赖。"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from .runtime import ControlError, digest_json, sha_file


REPOSITORY = Path(__file__).resolve().parents[2]
ENGINES = {
    "kohya": {"package": "kohya", "python": "3.10.19", "python_abi": "cp310", "upstream_commit": "trainer-source", "source": ".", "source_include_prefixes": ["scripts/", "vendor/sd-scripts/"], "entry": "scripts/stable/train_network.py", "imports": ["torch", "accelerate", "transformers", "diffusers"], "cuda": "cu128"},
    "anima-fast": {"package": "anima_fast", "python": "3.13", "python_abi": "cp313", "upstream_commit": "b43928b5e4b82b907bfca1a322383a33088d0bdd", "source": "vendor/anima_lora", "entry": "train.py", "imports": ["torch", "transformers", "diffusers", "flash_attn"], "cuda": "cu132"},
    "ai-toolkit": {"package": "ai_toolkit", "python": "3.11", "python_abi": "cp311", "upstream_commit": "ecee894ed2b1f3716d9d7326693061ec1a3105bb", "source": "vendor/ai-toolkit", "entry": "run.py", "imports": ["torch", "transformers", "diffusers"], "cuda": "cu128"},
    "diffsynth": {"package": "diffsynth", "python": "3.12", "python_abi": "cp312", "upstream_commit": "7686e54d41d25c0e8ed5f1318acc23b6bb832654", "source": "vendor/DiffSynth-Studio", "entry": "examples/qwen_image_21/model_training/train.py", "imports": ["torch", "diffsynth"], "cuda": "cu128"},
}


def assignments(path: Path) -> dict:
    values = {}
    for statement in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign):
            try:
                value = ast.literal_eval(statement.value)
            except (ValueError, TypeError):
                continue
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = value
    return values


def recipe(engine_id: str, repository: Path | None = None) -> dict:
    if engine_id not in ENGINES:
        raise ControlError("unsupported_engine", "该引擎没有版本化适配器")
    root = repository or REPOSITORY
    data = dict(ENGINES[engine_id])
    package = root / "mikazuki" / "engines" / data["package"]
    environment = assignments(package / "environment.py")
    manifest = assignments(package / "manifest.py")
    source_files = [package / name for name in ("manifest.py", "environment.py", "settings.py")]
    constraints = []
    if engine_id == "kohya":
        requirements = [*environment["TORCH_PINS"], environment["XFORMERS_PIN"], *environment["TRAINING_DEPS"]]
    elif engine_id == "anima-fast":
        path = root / "config/anima_fast_environment/anima-constraints-cu132.txt"
        constraints = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
        requirements = constraints + ["flash-attn @ " + environment["FLASH_ATTN_WINDOWS_CU132_URL"]]
        source_files.extend([path, root / "config/anima_fast_environment/anima-overrides-cu132.txt"])
    elif engine_id == "diffsynth":
        requirements = [*environment["TORCH_PINS"], "transformers>=4.57.1,<5", "tensorboard", "bitsandbytes==0.48.2", "opencv-python-headless==4.11.0.86"]
    else:
        # 固定官方 cu128 三件套，避免浮动索引优先级选到 PyPI CPU wheel。
        requirements = ["torch==2.11.0+cu128", "torchvision==0.26.0+cu128", "torchaudio==2.11.0+cu128"]
    if engine_id in {"ai-toolkit", "diffsynth"}:
        path = root / "mikazuki" / "launcher" / "requirements" / (engine_id + "-base.txt")
        requirements += [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
        source_files.append(path)
        if engine_id == "ai-toolkit":
            data["prebuilt_sources"] = [{"name": "diffusers", "repo": "huggingface/diffusers", "commit": "c943837899b16cbae2f619b8dd4f7bb6f07dd81a", "build_policy": "publisher pinned backend; embedded wheel sha256"}]
    upstream = manifest.get("UPSTREAM", {})
    data.update(schema_version=1, engine_id=engine_id, platform="windows-x86_64", ownership="standalone", gui_environment_fallback=False,
                upstream=upstream, requirements=requirements, constraints=constraints,
                source_fingerprint_encoding="utf8-lf-v1",
                source_fingerprints={p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in source_files},
                actions=["inspect_readonly", "probe_execute", "plan_install", "plan_repair", "repair_apply", "recover"],
                validation={"gpu": "skip + CR-004", "model": "skip + CR-004", "training": "skip + CR-004"},
                lock_status="requires_resolved_platform_asset_lock")
    data["recipe_sha256"] = digest_json(data)
    return data


def capabilities() -> dict:
    return {"schema_version": 1, "engines": [{"engine_id": key, "actions": ["inspect_readonly", "probe_execute", "plan_install", "plan_repair", "repair_apply", "recover"], "ownership": "standalone", "main_env_fallback": False, "runtime_contract": 1} for key in ENGINES], "worker_imports": "stdlib only", "network_owner": "launcher controlled asset downloader"}

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import json
import os
import subprocess

from .settings import RuntimeConfig


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".avif"}


@dataclass
class ProbeFacts:
    python_version: str = ""
    torch_version: str = ""
    torch_metadata_version: str = ""
    cuda_available: bool = False
    cuda_version: str = ""
    gpu_name: str = ""
    vram_total_mb: int = 0
    flash_attn_importable: bool = False
    triton_importable: bool = False
    quanto_importable: bool = False
    transformers_version: str = ""
    diffusers_version: str = ""


@dataclass
class PreflightResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "facts": self.facts,
        }


DependencyProbe = Callable[[RuntimeConfig], ProbeFacts]


def default_dependency_probe(runtime: RuntimeConfig) -> ProbeFacts:
    script = r"""
import importlib.metadata, importlib.util, json, platform
facts = {"python_version": platform.python_version()}
try:
    facts["torch_metadata_version"] = importlib.metadata.version("torch")
except Exception:
    facts["torch_metadata_version"] = ""
try:
    import torch
    facts["torch_version"] = getattr(torch, "__version__", "")
    facts["cuda_available"] = bool(torch.cuda.is_available())
    facts["cuda_version"] = getattr(torch.version, "cuda", "") or ""
    if torch.cuda.is_available():
        facts["gpu_name"] = torch.cuda.get_device_name(0)
        facts["vram_total_mb"] = int(torch.cuda.get_device_properties(0).total_memory // (1024 * 1024))
except Exception as exc:
    facts["torch_error"] = str(exc)
for name in ("flash_attn", "triton"):
    facts[name + "_importable"] = importlib.util.find_spec(name) is not None
facts["quanto_importable"] = importlib.util.find_spec("optimum.quanto") is not None
for name in ("transformers", "diffusers"):
    try:
        mod = __import__(name)
        facts[name + "_version"] = getattr(mod, "__version__", "")
    except Exception:
        facts[name + "_version"] = ""
print(json.dumps(facts))
"""
    env = os.environ.copy()
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1"})
    env.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [str(runtime.python), "-c", script],
        cwd=str(runtime.anima_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=env,
    )
    if completed.returncode != 0:
        return ProbeFacts()
    try:
        raw = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return ProbeFacts()
    return ProbeFacts(
        python_version=str(raw.get("python_version", "")),
        torch_version=str(raw.get("torch_version", "")),
        torch_metadata_version=str(raw.get("torch_metadata_version", "")),
        cuda_available=bool(raw.get("cuda_available", False)),
        cuda_version=str(raw.get("cuda_version", "")),
        gpu_name=str(raw.get("gpu_name", "")),
        vram_total_mb=int(raw.get("vram_total_mb", 0) or 0),
        flash_attn_importable=bool(raw.get("flash_attn_importable", False)),
        triton_importable=bool(raw.get("triton_importable", False)),
        quanto_importable=bool(raw.get("quanto_importable", False)),
        transformers_version=str(raw.get("transformers_version", "")),
        diffusers_version=str(raw.get("diffusers_version", "")),
    )


def _truthy(value: Any) -> bool:
    return value in (True, "true", "True", "1", 1)


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _resolve(value: Any, base: Path) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _resolution_tokens(config: dict[str, Any]) -> int:
    raw = config.get("resolution")
    if raw is None:
        return 0
    if isinstance(raw, int):
        width = height = raw
    else:
        text = str(raw).replace("x", ",").replace(" ", "")
        parts = [p for p in text.split(",") if p]
        if len(parts) == 1:
            width = height = _int_value(parts[0])
        elif len(parts) >= 2:
            width = _int_value(parts[0])
            height = _int_value(parts[1])
        else:
            return 0
    if width <= 0 or height <= 0:
        return 0
    return (width // 16) * (height // 16)


def _dataset_images(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]


def _has_files(root: Path | None, suffixes: set[str] | None = None) -> bool:
    if root is None or not root.is_dir():
        return False
    for path in root.rglob("*"):
        if path.is_file() and (suffixes is None or path.suffix.lower() in suffixes):
            return True
    return False


def run_preflight(config: dict[str, Any], runtime: RuntimeConfig, probe: DependencyProbe = default_dependency_probe) -> PreflightResult:
    errors: list[str] = []
    warnings: list[str] = []
    facts: dict[str, Any] = {
        "anima_root": str(runtime.anima_root),
        "python": str(runtime.python),
        "preflight_level": runtime.preflight_level,
    }

    if not runtime.anima_root.is_dir():
        errors.append(f"anima_root does not exist: {runtime.anima_root}")
    if not runtime.python.is_file():
        errors.append(f"anima_lora python does not exist: {runtime.python}")
    if not (runtime.anima_root / "train.py").is_file():
        errors.append(f"anima_lora train.py missing under {runtime.anima_root}")
    if not (runtime.anima_root / "configs" / "base.toml").is_file():
        errors.append("anima_lora configs/base.toml missing")

    for field in ("pretrained_model_name_or_path", "vae", "qwen3"):
        path = _resolve(config.get(field), runtime.lora_next_root)
        if path is None:
            errors.append(f"required model field missing: {field}")
        elif not path.is_file():
            errors.append(f"required model file does not exist: {field}={path}")

    train_dir = _resolve(config.get("train_data_dir") or config.get("source_image_dir"), runtime.lora_next_root)
    if train_dir is None:
        errors.append("train_data_dir/source_image_dir is required")
    elif not train_dir.is_dir():
        errors.append(f"training data directory does not exist: {train_dir}")
    else:
        images = _dataset_images(train_dir)
        facts["dataset_image_count"] = len(images)
        if not images:
            errors.append(f"no training images found under {train_dir}")
        stems: dict[str, Path] = {}
        duplicates: list[str] = []
        for image in images:
            if image.stem in stems:
                duplicates.append(image.stem)
            stems[image.stem] = image
        if duplicates:
            errors.append("duplicate image stems would collide in anima_lora flat cache: " + ", ".join(sorted(set(duplicates))[:8]))
        captioned = sum(1 for image in images if image.with_suffix(".txt").is_file())
        if images and captioned < len(images):
            warnings.append(f"{len(images) - captioned} image(s) do not have .txt captions")

    compile_mode = str(config.get("compile_mode", "blocks"))
    gradient_checkpointing = _truthy(config.get("gradient_checkpointing"))
    blocks_to_swap = _int_value(config.get("blocks_to_swap"), 0)
    cpu_offload = _truthy(config.get("cpu_offload_checkpointing"))
    unsloth = _truthy(config.get("unsloth_offload_checkpointing"))
    torch_compile = _truthy(config.get("torch_compile", True))
    static_token_count = _int_value(config.get("static_token_count"), 0)

    if compile_mode == "full" and gradient_checkpointing:
        errors.append("compile_mode=full is incompatible with gradient_checkpointing")
    if compile_mode == "full" and blocks_to_swap > 0:
        errors.append("compile_mode=full is incompatible with blocks_to_swap")
    if blocks_to_swap > 0 and cpu_offload:
        errors.append("blocks_to_swap is incompatible with cpu_offload_checkpointing")
    if unsloth and cpu_offload:
        errors.append("unsloth_offload_checkpointing is incompatible with cpu_offload_checkpointing")
    if unsloth and blocks_to_swap > 0:
        errors.append("unsloth_offload_checkpointing is incompatible with blocks_to_swap")
    if torch_compile and static_token_count <= 0:
        errors.append("torch_compile requires static_token_count")
    tokens = _resolution_tokens(config)
    facts["resolution_tokens"] = tokens
    if _truthy(config.get("enable_bucket", True)) and 0 < static_token_count < 4096:
        warnings.append("enable_bucket may create high-resolution Anima buckets; use static_token_count=4096 or higher")
    if torch_compile and tokens and static_token_count and tokens > static_token_count:
        errors.append(f"static_token_count={static_token_count} is smaller than resolution token count {tokens}")

    cache_latents = _truthy(config.get("cache_latents"))
    cache_text_encoder = _truthy(config.get("cache_text_encoder_outputs"))
    skip_cache_check = _truthy(config.get("skip_cache_check"))
    resized_dir = _resolve(config.get("resized_image_dir") or config.get("source_image_dir"), runtime.lora_next_root)
    lora_cache_dir = _resolve(config.get("lora_cache_dir"), runtime.lora_next_root)
    facts["cache_latents"] = cache_latents
    facts["cache_text_encoder_outputs"] = cache_text_encoder
    facts["skip_cache_check"] = skip_cache_check
    if resized_dir is not None:
        facts["resized_image_dir"] = str(resized_dir)
    if lora_cache_dir is not None:
        facts["lora_cache_dir"] = str(lora_cache_dir)
    if not skip_cache_check:
        if cache_latents and not _has_files(resized_dir, {".npz", ".safetensors", ".pt", ".pth"}):
            errors.append(
                "cache_latents=true requires completed Anima preprocess/cache files; "
                "disable cache_latents for live VAE encoding or run preprocess first"
            )
        if cache_text_encoder and not _has_files(lora_cache_dir, {".npz", ".safetensors", ".pt", ".pth"}):
            errors.append(
                "cache_text_encoder_outputs=true requires completed Anima text encoder cache; "
                "disable cache_text_encoder_outputs for live encoding or run preprocess first"
            )

    if not errors:
        dep = probe(runtime)
        facts.update(dep.__dict__)
        if not dep.python_version.startswith("3.13") and not runtime.allow_unsupported:
            errors.append(f"anima_lora requires Python 3.13.*, got {dep.python_version or 'unknown'}")
        if not dep.cuda_available:
            errors.append("torch.cuda is not available in anima_lora runtime")
        if not dep.torch_metadata_version:
            errors.append(
                "torch package metadata is missing (dist-info corrupt); "
                "repair the Anima Fast plugin before training"
            )
        optimizer_type = str(config.get("optimizer_type", "")).strip().lower()
        if optimizer_type == "automagic" and not dep.quanto_importable:
            errors.append(
                "optimizer_type=Automagic requires optimum-quanto in the Fast plugin venv; repair the plugin"
            )
        if str(config.get("attn_mode", "flash")) == "flash" and not dep.flash_attn_importable:
            errors.append("attn_mode=flash requested but flash_attn is not importable")
        if torch_compile and dep.vram_total_mb and dep.vram_total_mb < 14000:
            warnings.append(f"VRAM {dep.vram_total_mb} MB may be low for torch_compile + static_token_count=4096")
        if config.get("sample_prompts"):
            warnings.append(
                "sample_prompts is enabled; sampling loads VAE/Qwen3 during training and increases VRAM/time"
            )
            if dep.vram_total_mb and dep.vram_total_mb < 18000:
                warnings.append(
                    f"VRAM {dep.vram_total_mb} MB may be tight for torch_compile training with preview sampling"
                )

    return PreflightResult(ok=not errors, errors=errors, warnings=warnings, facts=facts)

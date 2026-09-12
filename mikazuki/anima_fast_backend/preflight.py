from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import json
import os
import re
import subprocess
import sys

from .extension_state import ExtensionLayout
from .settings import RuntimeConfig


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".avif"}
DIT_BLOCK_RE = re.compile(r"^blocks\.(\d+)\.")
DIT_PREFIXES = ("net.", "model.diffusion_model.")
DIT_SHARD_RE = re.compile(
    r"^(?P<prefix>.*)-(?P<index>\d{5})-of-(?P<total>\d{5})\.safetensors$"
)
MODEL_CHANNELS_TO_HEADS = {1280: 20, 2048: 16, 5120: 40}


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
    probe_error: str = ""


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


def _dit_checkpoint_files(path: Path) -> list[Path]:
    match = DIT_SHARD_RE.match(path.name)
    if not match:
        return [path]

    prefix = match.group("prefix")
    total = int(match.group("total"))
    index = int(match.group("index"))
    if total < 1 or not 1 <= index <= total:
        raise ValueError(f"invalid checkpoint shard declaration: {path.name}")

    declared_totals = {
        int(candidate_match.group("total"))
        for candidate in path.parent.glob(f"{prefix}-*-of-*.safetensors")
        if (candidate_match := DIT_SHARD_RE.match(candidate.name))
        and candidate_match.group("prefix") == prefix
    }
    if declared_totals != {total}:
        raise ValueError(
            "mixed checkpoint shard totals: "
            + ", ".join(f"{value:05d}" for value in sorted(declared_totals))
        )

    files = [
        path.parent / f"{prefix}-{shard_index:05d}-of-{total:05d}.safetensors"
        for shard_index in range(1, total + 1)
    ]
    missing = next((candidate for candidate in files if not candidate.is_file()), None)
    if missing is not None:
        raise ValueError(f"missing checkpoint shard: {missing}")
    return files


def probe_dit_checkpoint(path: Path) -> dict[str, Any] | None:
    if path.suffix.lower() != ".safetensors":
        return None
    from safetensors import safe_open

    files = _dit_checkpoint_files(path)

    max_idx = -1
    width: int | None = None
    for file in files:
        with safe_open(file, framework="pt", device="cpu") as handle:
            for key in handle.keys():
                clean = key
                for prefix in DIT_PREFIXES:
                    if clean.startswith(prefix):
                        clean = clean[len(prefix):]
                        break
                match = DIT_BLOCK_RE.match(clean)
                if match:
                    max_idx = max(max_idx, int(match.group(1)))
                elif clean == "x_embedder.proj.1.weight":
                    width = int(handle.get_slice(key).get_shape()[0])
    if max_idx < 0:
        raise ValueError("no top-level Anima DiT blocks found")
    if width not in MODEL_CHANNELS_TO_HEADS:
        raise ValueError(f"unsupported Anima DiT width: {width}")
    num_blocks = max_idx + 1
    return {
        "num_blocks": num_blocks,
        "model_channels": width,
        "num_heads": MODEL_CHANNELS_TO_HEADS[width],
        "model_variant": (
            "anima-2.9b"
            if num_blocks == 40 and width == 2048
            else "anima-base"
            if num_blocks == 28 and width == 2048
            else "anima-compatible"
        ),
    }


def read_network_num_blocks(path: Path) -> int | None:
    if path.suffix.lower() != ".safetensors" or not path.is_file():
        return None
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as handle:
        value = (handle.metadata() or {}).get("ss_num_blocks")
    return int(value) if value else None


def _validate_resume_state(path: Path) -> list[str]:
    errors: list[str] = []
    safe_model = path / "model.safetensors"
    legacy_model = path / "pytorch_model.bin"
    if safe_model.exists():
        try:
            from safetensors import safe_open

            with safe_open(safe_model, framework="pt", device="cpu") as handle:
                if not list(handle.keys()):
                    errors.append(
                        f"resume state model has no tensors: {safe_model}"
                    )
        except Exception as exc:
            errors.append(f"resume state model is invalid: {safe_model}: {exc}")
    elif not legacy_model.is_file() or legacy_model.stat().st_size == 0:
        errors.append(
            "resume state is missing model.safetensors or pytorch_model.bin: "
            + str(path)
        )

    for name in ("optimizer.bin", "scheduler.bin"):
        state_file = path / name
        if not state_file.is_file() or state_file.stat().st_size == 0:
            errors.append(f"resume state is missing {name}: {state_file}")

    train_state_file = path / "train_state.json"
    if not train_state_file.is_file():
        errors.append(
            f"resume state is missing train_state.json: {train_state_file}"
        )
    else:
        try:
            train_state = json.loads(train_state_file.read_text(encoding="utf-8"))
            current_step = train_state["current_step"]
            if (
                not isinstance(current_step, int)
                or isinstance(current_step, bool)
                or current_step < 0
            ):
                raise ValueError("current_step must be a non-negative integer")
        except Exception as exc:
            errors.append(f"resume train_state.json is invalid: {exc}")
    return errors


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
        detail = (completed.stderr or completed.stdout or "probe exited non-zero").strip()
        return ProbeFacts(probe_error=detail[:800])
    try:
        raw = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        stderr = (completed.stderr or completed.stdout or "invalid probe json").strip()
        return ProbeFacts(probe_error=stderr[:800])
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


def _validate_plugin_python(runtime: RuntimeConfig, errors: list[str]) -> None:
    if not runtime.python.is_file():
        return
    try:
        actual = runtime.python.resolve()
    except OSError:
        return
    if os.environ.get("ANIMA_LORA_PYTHON"):
        return
    try:
        if actual == Path(sys.executable).resolve():
            errors.append(
                "Fast 预检查误用了 GUI 主环境 Python（非插件 venv）；"
                "请在 Fast 页点击「修复插件」，或确认 extensions/anima_lora/.venv 已安装"
            )
            return
    except OSError:
        pass
    expected = ExtensionLayout(runtime.lora_next_root / "extensions" / "anima_lora").venv_python
    try:
        expected_resolved = expected.resolve()
    except OSError:
        return
    if expected_resolved.is_file() and actual != expected_resolved:
        parts = str(actual).replace("\\", "/").split("/")
        if "extensions/anima_lora/.venv" not in "/".join(parts):
            errors.append(
                f"Fast 应使用插件 venv Python（{expected_resolved}），当前为 {actual}；"
                "请修复插件或设置 ANIMA_LORA_PYTHON"
            )


def _image_pixel_size(path: Path) -> tuple[int, int] | None:
    try:
        import imagesize

        width, height = imagesize.get(path)
        if width > 0 and height > 0:
            return int(width), int(height)
    except Exception:
        pass
    try:
        from PIL import Image

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None


def _v117_latent_cache_ok(path: Path, width: int, height: int) -> bool:
    import numpy as np

    if width % 8 or height % 8:
        return False
    suffix = f"_{height // 8}x{width // 8}"
    latent_key = f"latents{suffix}"
    original_size_key = f"original_size{suffix}"
    crop_ltrb_key = f"crop_ltrb{suffix}"
    try:
        with np.load(path, allow_pickle=False) as data:
            if not {latent_key, original_size_key, crop_ltrb_key}.issubset(data.files):
                return False
            latents = data[latent_key]
            return bool(
                latents.ndim >= 3
                and latents.shape[-2:] == (height // 8, width // 8)
                and data[original_size_key].shape == (2,)
                and data[crop_ltrb_key].shape == (4,)
            )
    except Exception:
        return False


def _v117_text_cache_layout(
    keys: set[str],
    cache_llm_adapter_outputs: bool,
    suffix: str = "",
) -> tuple[str, ...] | None:
    stems = (
        ("crossattn_emb", "t5_attn_mask")
        if cache_llm_adapter_outputs
        else ("prompt_embeds", "attn_mask", "t5_input_ids", "t5_attn_mask")
    )
    required = tuple(f"{stem}{suffix}" for stem in stems)
    return required if set(required).issubset(keys) else None


def _v117_text_cache_ok(
    path: Path,
    *,
    cache_llm_adapter_outputs: bool,
) -> bool:
    from safetensors import safe_open

    try:
        with safe_open(path, framework="pt", device="cpu") as handle:
            keys = set(handle.keys())
            if "caption_dropout_rate" not in keys:
                return False
            if "num_variants" not in keys:
                return (
                    _v117_text_cache_layout(keys, cache_llm_adapter_outputs)
                    is not None
                )
            num_variants = int(handle.get_tensor("num_variants"))
            layout = _v117_text_cache_layout(keys, cache_llm_adapter_outputs, "_v0")
            if num_variants <= 0 or layout is None:
                return False
            stems = tuple(key.removesuffix("_v0") for key in layout)
            if not all(
                all(f"{stem}_v{index}" in keys for stem in stems)
                for index in range(num_variants)
            ):
                return False
            if "num_randomized" in keys:
                num_randomized = int(handle.get_tensor("num_randomized"))
                if num_randomized <= 0 or not all(
                    all(f"{stem}_r{index}" in keys for stem in stems)
                    for index in range(1, num_randomized + 1)
                ):
                    return False
            return True
    except Exception:
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
    else:
        _validate_plugin_python(runtime, errors)
    if not (runtime.anima_root / "train.py").is_file():
        errors.append(f"anima_lora train.py missing under {runtime.anima_root}")
    if not (runtime.anima_root / "configs" / "base.toml").is_file():
        errors.append("anima_lora configs/base.toml missing")

    model_path: Path | None = None
    for field in ("pretrained_model_name_or_path", "vae", "qwen3"):
        path = _resolve(config.get(field), runtime.lora_next_root)
        if path is None:
            errors.append(f"required model field missing: {field}")
        elif not path.is_file():
            errors.append(f"required model file does not exist: {field}={path}")
        elif field == "pretrained_model_name_or_path":
            model_path = path

    model_arch: dict[str, Any] | None = None
    if model_path is not None:
        try:
            model_arch = probe_dit_checkpoint(model_path)
            if model_arch:
                facts["anima_model"] = model_arch
                if model_arch["model_variant"] == "anima-2.9b":
                    warnings.append(
                        "Anima-2.9B is a 40-block checkpoint and requires more VRAM than Anima base"
                    )
        except Exception as exc:
            errors.append(f"invalid Anima DiT checkpoint: {exc}")

    metadata_paths: dict[str, Path] = {}
    for field in ("network_weights", "resume"):
        candidate = _resolve(config.get(field), runtime.lora_next_root)
        if candidate is None:
            continue
        if not candidate.exists():
            errors.append(f"{field} does not exist: {candidate}")
            continue
        if field == "network_weights":
            if not candidate.is_file() or candidate.suffix.lower() != ".safetensors":
                errors.append(f"network_weights must be a .safetensors file: {candidate}")
                continue
            metadata_paths[field] = candidate
            continue
        if not candidate.is_dir():
            errors.append(f"resume must be an Accelerate state directory: {candidate}")
            continue
        if not candidate.name.endswith("-state"):
            errors.append(f"resume must use the supported *-state directory layout: {candidate}")
            continue
        errors.extend(_validate_resume_state(candidate))
        companion = candidate.with_name(
            candidate.name.removesuffix("-state") + ".safetensors"
        )
        if not companion.is_file():
            errors.append(f"resume companion safetensors does not exist: {companion}")
            continue
        metadata_paths[field] = companion

    for field, metadata_path in metadata_paths.items():
        try:
            trained_blocks = read_network_num_blocks(metadata_path)
        except Exception as exc:
            errors.append(f"cannot read {field} metadata: {exc}")
            continue
        if (
            model_arch
            and trained_blocks
            and trained_blocks != model_arch["num_blocks"]
        ):
            errors.append(
                f"{field} was trained for {trained_blocks} Anima blocks "
                f"but the selected checkpoint has {model_arch['num_blocks']}"
            )

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
        captioned = sum(1 for image in images if image.with_suffix(".txt").is_file())
        if images and captioned < len(images):
            warnings.append(f"{len(images) - captioned} image(s) do not have .txt captions")

    blocks_to_swap = _int_value(config.get("blocks_to_swap"), 0)
    cpu_offload = _truthy(config.get("cpu_offload_checkpointing"))
    unsloth = _truthy(config.get("unsloth_offload_checkpointing"))
    torch_compile = _truthy(config.get("torch_compile", False))

    if blocks_to_swap > 0 and cpu_offload:
        errors.append("blocks_to_swap is incompatible with cpu_offload_checkpointing")
    if unsloth and cpu_offload:
        errors.append("unsloth_offload_checkpointing is incompatible with cpu_offload_checkpointing")
    if unsloth and blocks_to_swap > 0:
        errors.append("unsloth_offload_checkpointing is incompatible with blocks_to_swap")
    tokens = _resolution_tokens(config)
    facts["resolution_tokens"] = tokens
    if torch_compile and not _truthy(config.get("compile_dynamic_seq", True)):
        errors.append("torch_compile requires compile_dynamic_seq with Anima v1.17.1 free-fit buckets")
    raw_attn_mode = config.get("attn_mode")
    attn_mode = str(raw_attn_mode or "").strip()
    if attn_mode.lower() in {"", "undefined", "null", "nan"}:
        attn_mode = "torch"
    if attn_mode == "torch" and torch_compile:
        errors.append(
            "attn_mode=torch cannot be combined with torch_compile=true in Anima Fast "
            "(#336); disable torch_compile or choose a supported attention mode"
        )

    optimizer_type = str(config.get("optimizer_type", "")).strip().lower()
    if optimizer_type == "automagic":
        errors.append(
            "optimizer_type=Automagic is not supported by the Anima Fast plugin runtime; "
            "use AdamW8bit or another Fast optimizer"
        )

    cache_latents = _truthy(config.get("use_vae_cache"))
    cache_text_encoder = _truthy(config.get("use_text_cache"))
    cache_llm_adapter_outputs = _truthy(
        config.get("cache_llm_adapter_outputs", False)
    )
    skip_cache_check = _truthy(config.get("skip_cache_check"))
    resized_dir = _resolve(config.get("resized_image_dir") or config.get("source_image_dir"), runtime.lora_next_root)
    lora_cache_dir = _resolve(config.get("lora_cache_dir"), runtime.lora_next_root)
    facts["use_vae_cache"] = cache_latents
    facts["use_text_cache"] = cache_text_encoder
    facts["skip_cache_check"] = skip_cache_check
    if resized_dir is not None:
        facts["resized_image_dir"] = str(resized_dir)
    if lora_cache_dir is not None:
        facts["lora_cache_dir"] = str(lora_cache_dir)
    cache_enabled = cache_latents or cache_text_encoder
    resized_images: list[Path] = []
    cache_dir_ready = False
    if cache_enabled:
        if resized_dir is None:
            errors.append("resized_image_dir is required when cache loading is enabled")
        elif not resized_dir.is_dir():
            errors.append(f"resized_image_dir does not exist: {resized_dir}")
        else:
            resized_images = _dataset_images(resized_dir)
            if not resized_images:
                errors.append(
                    f"resized_image_dir contains no supported images: {resized_dir}"
                )
        if lora_cache_dir is None:
            errors.append("lora_cache_dir is required when cache loading is enabled")
        elif not lora_cache_dir.is_dir():
            errors.append(f"lora_cache_dir does not exist: {lora_cache_dir}")
        else:
            cache_dir_ready = True
    if resized_images and cache_dir_ready:
        missing_latents: list[str] = []
        invalid_latents: list[str] = []
        missing_text: list[str] = []
        invalid_text: list[str] = []
        unreadable: list[str] = []
        for image in resized_images:
            rel = image.relative_to(resized_dir).with_suffix("")
            identity = rel.as_posix()
            if cache_latents:
                size = _image_pixel_size(image)
                if size is None:
                    unreadable.append(identity)
                else:
                    width, height = size
                    npz = (
                        lora_cache_dir
                        / rel.parent
                        / f"{rel.name}_{width:04d}x{height:04d}_anima.npz"
                    )
                    if not npz.is_file():
                        missing_latents.append(identity)
                    elif not skip_cache_check and not _v117_latent_cache_ok(
                        npz, width, height
                    ):
                        invalid_latents.append(identity)
            if cache_text_encoder:
                te = lora_cache_dir / rel.parent / f"{rel.name}_anima_te.safetensors"
                if not te.is_file():
                    missing_text.append(identity)
                elif not skip_cache_check and not _v117_text_cache_ok(
                    te, cache_llm_adapter_outputs=cache_llm_adapter_outputs
                ):
                    invalid_text.append(identity)
        if unreadable:
            errors.append(
                "cannot read image dimensions for resized images: "
                + ", ".join(sorted(unreadable)[:8])
            )
        if missing_latents:
            errors.append(
                "use_vae_cache=true is missing cache files for resized images: "
                + ", ".join(sorted(missing_latents)[:8])
            )
        elif invalid_latents:
            errors.append(
                "use_vae_cache=true requires completed Anima preprocess/cache files; "
                "disable use_vae_cache for live VAE encoding or run preprocess first: "
                + ", ".join(sorted(invalid_latents)[:8])
            )
        if missing_text:
            errors.append(
                "use_text_cache=true is missing cache files for resized images: "
                + ", ".join(sorted(missing_text)[:8])
            )
        elif invalid_text:
            errors.append(
                "use_text_cache=true requires completed Anima text encoder cache; "
                "disable use_text_cache for live encoding or run preprocess first: "
                + ", ".join(sorted(invalid_text)[:8])
            )

    if not errors:
        dep = probe(runtime)
        facts.update(dep.__dict__)
        if dep.probe_error:
            errors.append(
                f"anima_lora runtime probe failed using {runtime.python}: {dep.probe_error}"
            )
        if not dep.python_version.startswith("3.13") and not runtime.allow_unsupported:
            errors.append(f"anima_lora requires Python 3.13.*, got {dep.python_version or 'unknown'}")
        if not dep.cuda_available:
            errors.append("torch.cuda is not available in anima_lora runtime")
        if not dep.torch_metadata_version:
            errors.append(
                "torch package metadata is missing (dist-info corrupt); "
                "repair the Anima Fast plugin before training"
            )
        if str(config.get("attn_mode", "")).strip() == "flash" and not dep.flash_attn_importable:
            errors.append(
                "attn_mode=flash 需要 Fast 插件环境可导入 flash_attn；"
                "请改用 torch/xformers，或先修复插件环境"
            )
        if torch_compile and dep.vram_total_mb and dep.vram_total_mb < 14000:
            warnings.append(
                f"VRAM {dep.vram_total_mb} MB may be low for torch_compile with free-fit buckets"
            )
        if config.get("sample_prompts"):
            warnings.append(
                "sample_prompts is enabled; sampling loads VAE/Qwen3 during training and increases VRAM/time"
            )
            if dep.vram_total_mb and dep.vram_total_mb < 18000:
                warnings.append(
                    f"VRAM {dep.vram_total_mb} MB may be tight for torch_compile training with preview sampling"
                )

    return PreflightResult(ok=not errors, errors=errors, warnings=warnings, facts=facts)

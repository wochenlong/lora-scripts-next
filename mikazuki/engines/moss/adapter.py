"""Next Trainer form -> the pinned MOSS CacheRequest / TrainRequest flags.

MOSS has no Anima TOML chain. Keep its native names and semantics; the only
path conversion is Next Trainer's output_dir/output_name and cache_dir.
This module intentionally never imports torch or the training environment.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys


TARGETS = r"layers\.\d+\.proj\.(q|k|v|o|ffn_up_gate|ffn_down)"
TRAIN_DEFAULTS = {
    "model": "base", "epochs": 8, "max_steps": 0, "rank": 16,
    "batch_size": 1, "preview_every_epochs": 0, "preview_prompt_file": "",
    "preview_width": 1024, "preview_height": 1024, "preview_steps": 30, "preview_seed": 42,  # preview_prompt is UI-only
    "lr": 1e-4, "warmup_ratio": 0.05, "save_every_epochs": 0,
    "caption_dropout": 0.0, "lora_dtype": "bf16", "targets": TARGETS,
    "sigma_mu": -1.09, "sigma_s": 0.95, "sigma_cutoff": 0.95,
    "sigma_uniform": 0.01, "max_grad_norm": 1.0,
    "grad_checkpointing": True, "blocks_to_swap": 0,
    # Safer first launch and portable Windows default; explicitly emitted.
    "compile": False, "log_every": 10, "seed": 0,
}
CACHE_DEFAULTS = {
    "resolution": 1024, "save_crops": False,
    "vae_dtype": "fp32", "max_text_tokens": 4096,
}
UI_FIELDS = {
    "model_train_type", "gpu_ids", "src", "model_dir", "cache_dir",
    "output_dir", "output_name", "run_preprocess", "overwrite_cache",
    "model_input_mode", "dit_path", "text_encoder_path", "vae_path",
    "tokenizer_path", "sft_dit_path", "preview_prompt",
}
INT_BOUNDS = {
    "epochs": (0, None), "max_steps": (0, None), "rank": (1, 3072),
    "batch_size": (1, 2), "preview_every_epochs": (0, None),
    "preview_width": (16, 2048), "preview_height": (16, 2048),
    "preview_steps": (1, 100), "preview_seed": (0, 2**63 - 1),
    "save_every_epochs": (0, None), "blocks_to_swap": (-1, 40),
    "log_every": (1, None), "seed": (0, 2**63 - 1),
    "resolution": (16, 4096), "max_text_tokens": (1, 4096),
}
FLOAT_BOUNDS = {
    "lr": (0, None, False), "alpha": (0, None, False),
    "warmup_ratio": (0, 1, True), "caption_dropout": (0, 1, True),
    "sigma_mu": (-20, 20, True), "sigma_s": (0, 20, False),
    "sigma_cutoff": (0, 1, False), "sigma_uniform": (0, 1, True),
    "max_grad_norm": (0, None, False),
}


def absolute(value, root):
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = root / path
    return Path(os.path.abspath(str(path)))


def _empty(value):
    return value is None or isinstance(value, str) and not value.strip()


def _bool(value, key):
    if value is True or value == "true":
        return True
    if value is False or value == "false":
        return False
    raise ValueError(f"{key}: expected true/false / 必须为布尔值")


def _number(value, key, *, integer=False):
    if isinstance(value, bool):
        raise ValueError(f"{key}: expected a number / 必须为数值")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key}: expected a number / 必须为数值") from exc
    if not math.isfinite(number) or integer and not number.is_integer():
        raise ValueError(f"{key}: invalid numeric value / 数值无效")
    return int(number) if integer else number


def argv_for(values):
    """BooleanOptionalAction spells false as --no-<name>, including underscores."""
    argv = []
    for key, value in values.items():
        if isinstance(value, bool):
            argv.append(f"--{key}" if value else f"--no-{key}")
        elif value is not None:
            argv.extend([f"--{key}", str(value)])
    return argv


@dataclass
class AdaptedConfig:
    cache: dict
    train: dict
    run_preprocess: bool
    warnings: list[str]
    model_input_mode: str = "native_directory"
    comfy_paths: dict | None = None

    def as_dict(self):
        return asdict(self)


def adapt_config(config, runtime):
    from .comfy import comfy_layout_digest

    allowed = set(TRAIN_DEFAULTS) | set(CACHE_DEFAULTS) | UI_FIELDS | {"alpha"}
    unknown = sorted(key for key, value in config.items() if key not in allowed and not _empty(value))
    if unknown:
        raise ValueError("Unsupported MOSS fields / 不支持的 MOSS 参数: " + ", ".join(unknown))
    train, cache = dict(TRAIN_DEFAULTS), dict(CACHE_DEFAULTS)
    for key in set(train) | set(cache) | {"alpha"}:
        if key not in config or _empty(config[key]):
            continue
        target = cache if key in cache else train
        value = config[key]
        if key in INT_BOUNDS:
            value = _number(value, key, integer=True)
            low, high = INT_BOUNDS[key]
            if value < low or high is not None and value > high:
                raise ValueError(f"{key}: outside supported range [{low}, {high}] / 超出范围")
        elif key in FLOAT_BOUNDS:
            value = _number(value, key)
            low, high, inclusive = FLOAT_BOUNDS[key]
            if value < low or not inclusive and value == low or high is not None and value > high:
                raise ValueError(f"{key}: outside supported range / 超出支持范围")
        elif isinstance(target.get(key), bool):
            value = _bool(value, key)
        else:
            value = str(value).strip()
        target[key] = value
    if train["model"] not in {"base", "sft"}:
        raise ValueError("model: choose base or sft / 请选择 Base 或 SFT")
    if train["lora_dtype"] not in {"bf16", "fp16", "fp32"}:
        raise ValueError("lora_dtype: choose bf16, fp16 or fp32")
    if cache["vae_dtype"] not in {"fp32", "bf16"}:
        raise ValueError("vae_dtype: choose fp32 or bf16")
    if not train["epochs"] and not train["max_steps"]:
        raise ValueError("epochs/max_steps: at least one must be positive / 至少一项必须大于 0")
    if sys.platform == "win32" and train["compile"]:
        raise ValueError("compile: disable torch.compile on Windows / Windows 请关闭编译")
    try:
        pattern = re.compile(train["targets"])
    except re.error as exc:
        raise ValueError(f"targets: invalid regular expression / 正则无效: {exc}") from exc
    names = [f"layers.{i}.proj.{name}" for i in range(42)
             for name in ("q", "k", "v", "o", "ffn_up_gate", "ffn_down")]
    if not any(pattern.fullmatch(name) for name in names):
        raise ValueError("targets: matches no MOSS LoRA layers / 未匹配任何 MOSS LoRA 层")
    mode = str(config.get("model_input_mode") or "native_directory").strip()
    if mode not in {"native_directory", "comfyui_files"}:
        raise ValueError("model_input_mode: choose native_directory or comfyui_files")
    for key in ("output_dir", "output_name"):
        if _empty(config.get(key)):
            raise ValueError(f"{key}: required / 必填")
    name = str(config["output_name"]).strip()
    if name in {".", ".."} or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith((".", " ")):
        raise ValueError("output_name: use a filename without directory separators / 请填写文件名而非路径")
    if name.lower().endswith(".safetensors"):
        name = name[:-12]
    if not name:
        raise ValueError("output_name: required / 必填")
    comfy_paths = None
    if mode == "comfyui_files":
        required = ("dit_path", "text_encoder_path", "vae_path", "tokenizer_path")
        for key in required:
            if _empty(config.get(key)):
                raise ValueError(f"{key}: required for Comfy mode / Comfy 模式必填")
        if train["model"] == "sft" and _empty(config.get("sft_dit_path")):
            raise ValueError("sft_dit_path: required when model=sft / SFT 需要单独的 DiT 文件")
        comfy_paths = {key: str(absolute(config[key], runtime.project_root)) for key in required}
        if not _empty(config.get("sft_dit_path")):
            comfy_paths["sft_dit_path"] = str(absolute(config["sft_dit_path"], runtime.project_root))
        digest = comfy_layout_digest(comfy_paths, model=train["model"])
        model_dir = absolute(runtime.project_root / ".cache" / "moss" / "comfy-layout" / digest, runtime.project_root)
    else:
        if _empty(config.get("model_dir")):
            raise ValueError("model_dir: required / 必填")
        model_dir = absolute(config["model_dir"], runtime.project_root)
    output = absolute(config["output_dir"], runtime.project_root) / f"{name}.safetensors"
    run_preprocess = _bool(config.get("run_preprocess", True), "run_preprocess")
    src = absolute(config["src"], runtime.project_root) if not _empty(config.get("src")) else None
    if run_preprocess and src is None:
        raise ValueError("src: required when preprocessing / 预处理需要数据集目录")
    if not run_preprocess and _empty(config.get("cache_dir")):
        raise ValueError("cache_dir: required without preprocessing / 跳过预处理时必填")
    identity = {"src": str(src), "model_dir": str(model_dir), "model_input_mode": mode, **cache}
    if comfy_paths is not None:
        identity["comfy_paths"] = comfy_paths
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    cache_dir = absolute(config.get("cache_dir") or runtime.project_root / ".cache" / "moss" / digest, runtime.project_root)
    cache.update(out=str(cache_dir), model_dir=str(model_dir), overwrite=_bool(config.get("overwrite_cache", False), "overwrite_cache"))
    if src is not None:
        cache["src"] = str(src)
    train.update(cache=str(cache_dir), model_dir=str(model_dir), output=str(output))
    train["preview_caption_sha256"] = ""
    if train["preview_every_epochs"]:
        if train["blocks_to_swap"] != 0:
            raise ValueError("preview_every_epochs: previews currently require blocks_to_swap=0")
        if train["preview_width"] % 16 or train["preview_height"] % 16:
            raise ValueError("preview_width/height must be multiples of 16")
        prompt_text = str(config.get("preview_prompt") or "").strip()
        if prompt_text:
            prompt_dir = runtime.project_root / ".cache" / "moss" / "preview-prompts"
            prompt_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]
            prompt_file = prompt_dir / f"{digest}.txt"
            payload = prompt_text if prompt_text.endswith("\n") else prompt_text + "\n"
            if not prompt_file.is_file() or prompt_file.read_text(encoding="utf-8") != payload:
                prompt_file.write_text(payload, encoding="utf-8")
            train["preview_prompt_file"] = str(prompt_file.resolve())
            train["preview_caption_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        else:
            prompt_file = absolute(train["preview_prompt_file"], runtime.project_root)
            if not train["preview_prompt_file"] or not prompt_file.is_file() or prompt_file.suffix.lower() != ".txt":
                raise ValueError(
                    "preview_prompt / preview_prompt_file: enter a preview caption or choose a local TXT / "
                    "请填写预览提示词或选择 TXT 文件"
                )
            raw = prompt_file.read_bytes()
            if not raw.decode("utf-8").strip():
                raise ValueError("preview_prompt_file: caption is empty")
            train["preview_prompt_file"] = str(prompt_file)
            train["preview_caption_sha256"] = hashlib.sha256(raw).hexdigest()
    warnings = ["MOSS upstream is alpha; use matching MOSS model weights. / MOSS 上游为 alpha，请使用对应的 MOSS 模型权重。"]
    if mode == "comfyui_files":
        warnings.append(
            "Comfy files are staged into a native Diffusers layout (hardlink/symlink/copy); "
            "Comfy-Org fused qkv DiT is split to q/k/v once in the staging tree. / "
            "Comfy 单文件会物化为原生 Diffusers 目录（优先硬链/符号链接）；"
            "Comfy-Org 融合 qkv 的 DiT 会在物化时拆成 q/k/v。"
        )
    if train["epochs"] and train["max_steps"]:
        warnings.append("max_steps caps epochs × shape-bucket batches; partial tails are retained. / 步数上限截断轮数 × 同形状批次数，保留尾批。")
    if not run_preprocess:
        warnings.append("External cache headers cannot prove model/caption provenance; only reuse caches for these exact assets. / 外部缓存头不能证明模型和标注来源，请仅复用对应模型的缓存。")
    return AdaptedConfig(cache, train, run_preprocess, warnings, mode, comfy_paths)


def dump_config(adapted, directory, run_id):
    path = Path(directory) / f"{run_id}-moss.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(adapted.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path.resolve()

"""Next Trainer form to a checked kogine Python config."""
import math
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from mikazuki.engines.moss.comfy import comfy_layout_digest

SUPPORTED_FIELDS = {
    "model_train_type",
    "model_input_mode", "pretrained_model_name_or_path", "model_variant",
    "dit_path", "text_encoder_path", "vae_path", "tokenizer_path", "sft_dit_path",
    "train_data_dir",
    "output_dir", "output_name",
    "max_train_steps", "max_train_epochs", "save_every_n_steps", "save_minutes", "keep_last",
    "seed", "log_every",
    "batching", "batch_size", "max_tokens", "max_samples", "grad_acc",
    "resolution_mode", "target_area", "caption_mode",
    "latent_cache", "text_cache", "cache_dir", "cache_dtype",
    "optimizer_type", "learning_rate", "weight_decay", "grad_clip", "ema",
    "lr_scheduler_mode", "lr_warmup_steps", "lr_schedule_end", "lr_min_value",
    "sample_every_n_steps", "sample_prompts", "sample_negative",
    "sample_width", "sample_height", "sample_steps", "sample_cfg", "sample_shift", "sample_seed",
    "network_algorithm", "network_preset", "network_dora", "network_dora_detach",
    "train_norm", "adapter_mode", "loraplus_ratio",
    "dropout_input", "dropout_rank", "dropout_module",
    "network_dim", "network_alpha",
    "lokr_factor", "lokr_full_matrix", "lokr_decompose_both",
    "oft_constraint", "oft_rescaled",
    "use_tucker", "use_scalar", "rank_dropout_scale",
    "dylora_block_size", "ia3_train_on_input",
    "tlora_mask_min_rank", "tlora_mask_alpha", "tlora_mask_max_timestep",
    "memory_profile", "mixed_precision", "base_precision", "fp16_fix",
    "fp8_recipe", "fp8_dgrad",
    "compile_mode", "tune_mode", "retune_steps",
    "parallel_mode", "devices", "gpu_ids", "pipeline_schedule", "microbatches",
}
ALGORITHMS = {"lora", "locon", "loha", "lokr", "oft", "boft", "glora", "ia3", "dylora", "tlora"}
PRESETS = {"attn", "attn-mlp", "full-block", "all"}
MEMORY_PROFILES = {"speed", "balanced", "low", "minimal", "auto"}
OPTIMIZERS = {"adamw", "adamw16", "adamw8bit", "adamw8bit_kernel", "muon", "prodigy", "schedule_free"}
BATCHINGS = {"tokens", "tokens_ffd", "count"}
CACHE_MODES = {"off", "offline", "online"}
VARIANTS = {"base", "sft"}
BASE_PRECISIONS = {"compute", "int8", "fp8", "fp8_compute", "mxfp8", "quant"}
PARALLEL_MODES = {"none", "ddp", "fsdp", "pipeline", "threaded"}


@dataclass
class AdaptedConfig:
    values: dict
    warnings: list[str]
    model_input_mode: str = "native_directory"
    comfy_paths: dict | None = None
    staging_root: str | None = None

    def as_dict(self):
        return asdict(self)


def _absolute(value, root):
    path = Path(str(value)).expanduser()
    return Path(os.path.abspath(path if path.is_absolute() else root / path))


def _integer(value, key, minimum=0):
    if isinstance(value, bool):
        raise ValueError(f"{key}: 必须为整数")  # noqa: TRY004 - form validation uses ValueError at the API boundary
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key}: 必须为整数") from exc
    if result < minimum:
        raise ValueError(f"{key}: 必须不小于 {minimum}")
    return result


def _float(value, key, minimum=None):
    if isinstance(value, bool):
        raise ValueError(f"{key}: 必须为数字")  # noqa: TRY004 - form validation uses ValueError at the API boundary
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key}: 必须为数字") from exc
    if not math.isfinite(result):
        raise ValueError(f"{key}: 必须为有限数")
    if minimum is not None and result < minimum:
        raise ValueError(f"{key}: 必须不小于 {minimum}")
    return result


def _bool(value, default=False):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _choice(value, key, allowed, default):
    text = str(value if value not in (None, "") else default).strip().lower()
    if text not in allowed:
        raise ValueError(f"{key}: 请选择 {' / '.join(sorted(allowed))}")
    return text


def _prompt_list(value):
    text = str(value or "").strip()
    if not text:
        return []
    return [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]


def _devices(value):
    text = str(value or "0").strip()
    if not text:
        return (0,)
    parts = []
    for item in text.replace(" ", "").split(","):
        if not item:
            continue
        parts.append(_integer(item, "devices", 0))
    return tuple(parts) or (0,)


def _algo_kwargs(config, algorithm):
    if algorithm == "lokr":
        return {
            "factor": _integer(config.get("lokr_factor", 8), "lokr_factor", -1),
            "full_matrix": _bool(config.get("lokr_full_matrix"), False),
            "decompose_both": _bool(config.get("lokr_decompose_both"), False),
            "use_tucker": _bool(config.get("use_tucker"), False),
            "rank_dropout_scale": _bool(config.get("rank_dropout_scale"), False),
        }
    if algorithm in {"oft", "boft"}:
        return {
            "constraint": _float(config.get("oft_constraint", 0.0), "oft_constraint", 0.0),
            "rescaled": _bool(config.get("oft_rescaled"), False),
        }
    if algorithm in {"lora", "locon", "loha"}:
        return {
            "use_tucker": _bool(config.get("use_tucker"), False),
            "use_scalar": _bool(config.get("use_scalar"), False),
            "rank_dropout_scale": _bool(config.get("rank_dropout_scale"), False),
        }
    if algorithm == "dylora":
        return {"block_size": _integer(config.get("dylora_block_size", 4), "dylora_block_size", 1)}
    if algorithm == "ia3":
        return {"train_on_input": _bool(config.get("ia3_train_on_input"), False)}
    if algorithm == "tlora":
        return {
            "mask_min_rank": _integer(config.get("tlora_mask_min_rank", 1), "tlora_mask_min_rank", 1),
            "mask_alpha": _float(config.get("tlora_mask_alpha", 1.0), "tlora_mask_alpha", 0.0),
            "mask_max_timestep": _float(config.get("tlora_mask_max_timestep", 1000.0), "tlora_mask_max_timestep", 1.0),
        }
    return {}


def _resolve_native_weights(raw_path: Path, variant: str) -> tuple[Path, Path | None]:
    """Resolve either a direct pipeline dir (`transformer/`) or a parent dir (`MOSS-Image-Base/`)."""
    if (raw_path / "transformer").is_dir():
        return raw_path, None
    sub_name = "MOSS-Image-SFT" if variant == "sft" else "MOSS-Image-Base"
    candidate = raw_path / sub_name
    base_dir = raw_path / "MOSS-Image-Base"
    if (candidate / "transformer").is_dir():
        # If SFT folder only holds transformer/, point encoders at MOSS-Image-Base
        if variant == "sft" and not (candidate / "text_encoder").is_dir() and base_dir.is_dir():
            return candidate, base_dir
        return candidate, None
    return raw_path, None


def _resolve_comfy_weight_path(value, root: Path) -> Path:
    path = _absolute(value, root)
    if path.is_dir():
        candidates = sorted(path.glob("*.safetensors"))
        if len(candidates) == 1:
            return candidates[0].resolve()
    return path


def _encode_settings(profile: str) -> tuple[dict, dict | None]:
    if profile == "minimal":
        return (
            {"memory": "stream", "ahead": 8, "batch": 16, "max_tokens": 8192, "pinned": False},
            {"memory": "offload", "ahead": 8, "tile": True},
        )
    if profile == "low":
        return {"memory": "stream", "ahead": 4}, None
    if profile == "auto":
        return {"memory": "auto", "ahead": 4}, {"memory": "auto"}
    return {"memory": "stream", "ahead": 8}, None


def adapt_config(config, runtime):
    unknown = sorted(key for key, value in config.items() if key not in SUPPORTED_FIELDS and value not in (None, ""))
    if unknown:
        raise ValueError("Unsupported KohakuMoss fields / 不支持的参数: " + ", ".join(unknown))

    raw_mode = str(config.get("model_input_mode") or "").strip().lower()
    if not raw_mode:
        if str(config.get("pretrained_model_name_or_path") or "").strip():
            raw_mode = "native_directory"
        elif any(str(config.get(k) or "").strip() for k in ("dit_path", "text_encoder_path", "vae_path", "tokenizer_path")):
            raw_mode = "comfyui_files"
        else:
            raw_mode = "native_directory"
    mode = _choice(raw_mode, "model_input_mode", {"native_directory", "comfyui_files"}, "native_directory")
    variant = _choice(config.get("model_variant"), "model_variant", VARIANTS, "base")

    if mode == "comfyui_files":
        comfy_required = ("dit_path", "text_encoder_path", "vae_path", "tokenizer_path")
        required = (*comfy_required, "train_data_dir", "output_dir", "output_name")
    else:
        comfy_required = ()
        required = ("pretrained_model_name_or_path", "train_data_dir", "output_dir", "output_name")

    missing = [key for key in required if not str(config.get(key) or "").strip()]
    if missing:
        raise ValueError("Missing required fields / 缺少必填项: " + ", ".join(missing))

    name = str(config["output_name"]).strip()
    if name in {".", ".."} or re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise ValueError("output_name: 请填写不含路径分隔符的文件名")

    steps = _integer(config.get("max_train_steps", 1000), "max_train_steps", 1)
    epochs = _integer(config.get("max_train_epochs", 0), "max_train_epochs")
    algorithm = _choice(config.get("network_algorithm"), "network_algorithm", ALGORITHMS, "lokr")
    preset = _choice(config.get("network_preset"), "network_preset", PRESETS, "attn-mlp")
    profile = _choice(config.get("memory_profile"), "memory_profile", MEMORY_PROFILES, "balanced")
    precision = _choice(config.get("mixed_precision"), "mixed_precision", {"bf16", "fp16", "auto"}, "bf16")
    batching = _choice(config.get("batching"), "batching", BATCHINGS, "tokens")
    optimizer = _choice(config.get("optimizer_type"), "optimizer_type", OPTIMIZERS, "adamw")
    base_precision = _choice(config.get("base_precision"), "base_precision", BASE_PRECISIONS, "compute")
    parallel = _choice(config.get("parallel_mode"), "parallel_mode", PARALLEL_MODES, "none")
    adapter_mode = _choice(config.get("adapter_mode"), "adapter_mode", {"bypass", "merge"}, "bypass")
    latent_cache = _choice(config.get("latent_cache"), "latent_cache", CACHE_MODES, "online")
    text_cache = _choice(config.get("text_cache"), "text_cache", CACHE_MODES, "online")
    cache_dtype = _choice(config.get("cache_dtype"), "cache_dtype", {"bf16", "fp8"}, "bf16")
    resolution_mode = _choice(
        config.get("resolution_mode"), "resolution_mode",
        {"resize", "bucket", "shifted_square", "square_crop"}, "bucket",
    )
    caption_mode = _choice(config.get("caption_mode"), "caption_mode", {"nl", "tags"}, "nl")
    compile_mode = _choice(config.get("compile_mode"), "compile_mode", {"off", "block", "model"}, "off")
    tune_mode = _choice(config.get("tune_mode"), "tune_mode", {"table", "off"}, "table")
    schedule_mode = _choice(config.get("lr_scheduler_mode"), "lr_scheduler_mode", {"cosine", "linear", "constant"}, "cosine")

    warmup = _integer(config.get("lr_warmup_steps", 100), "lr_warmup_steps")
    schedule_end = _integer(config.get("lr_schedule_end", -1), "lr_schedule_end", -1)
    if warmup >= (steps if schedule_end == -1 else schedule_end):
        raise ValueError("lr_warmup_steps: 必须小于 lr_schedule_end（-1 时为 max_train_steps）")

    raw_sample_every = _integer(config.get("sample_every_n_steps", 0), "sample_every_n_steps")
    prompts = _prompt_list(config.get("sample_prompts"))
    sample_every = raw_sample_every if prompts else 0
    dora = _bool(config.get("network_dora"), False)
    train_norms = _bool(config.get("train_norm"), False)
    if algorithm == "ia3" and train_norms:
        raise ValueError("train_norm: (IA)^3 不支持 TRAIN_NORMS")
    if algorithm == "tlora" and adapter_mode != "bypass":
        raise ValueError("adapter_mode: T-LoRA 仅支持 bypass")
    if dora and _float(config.get("dropout_input", 0), "dropout_input", 0.0) > 0:
        raise ValueError("dropout_input: DoRA 不支持输入 dropout")

    dim = 1 if algorithm == "ia3" else _integer(config.get("network_dim", 32), "network_dim", 1)
    alpha = 1.0 if algorithm == "ia3" else _float(config.get("network_alpha", config.get("network_dim", 32)), "network_alpha", 0.0)
    # gpu_ids selects visible physical GPUs in the launcher; DEVICES is local
    # to that visible set and must match preflight and /api/run (which pops gpu_ids).
    devices = _devices(config.get("devices") or "0")
    gpu_ids = config.get("gpu_ids")
    if gpu_ids is not None and (not isinstance(gpu_ids, list) or any(not str(gpu).isdigit() for gpu in gpu_ids)):
        raise ValueError("gpu_ids: 必须为 GPU 编号列表")
    if len(set(devices)) != len(devices) or (gpu_ids and max(devices) >= len(gpu_ids)):
        raise ValueError("devices: 编号不能重复，且必须位于 gpu_ids 选定的可见 GPU 集合内（从 0 开始）")
    if parallel == "none" and len(devices) > 1:
        raise ValueError("devices: parallel_mode=none 只能选择一张 GPU")
    if parallel != "none" and sys.platform == "win32":
        raise ValueError("parallel_mode: 上游多卡训练仅支持 Linux；Windows 请使用 none")
    if profile in {"low", "minimal"} and optimizer != "adamw":
        raise ValueError("optimizer_type: low / minimal 的流式优化器仅支持 adamw；其他优化器请选择 balanced / speed / auto")
    if parallel in {"fsdp", "pipeline", "threaded"}:
        if profile not in {"speed", "auto"} or base_precision != "compute":
            raise ValueError("parallel_mode: fsdp / pipeline / threaded 需要 memory_profile=speed 或 auto，且 base_precision=compute")
        if sample_every:
            raise ValueError("sample_every_n_steps: fsdp / pipeline / threaded 不支持训练中预览，请设为 0")
    if parallel == "fsdp" and optimizer == "muon":
        raise ValueError("optimizer_type: muon 不支持 fsdp，请使用 ddp 或其他优化器")
    max_samples = _integer(config.get("max_samples", 0), "max_samples")
    if parallel == "pipeline" and (batching == "count" or max_samples < 1 or text_cache != "offline"):
        raise ValueError("parallel_mode: pipeline 需要 tokens / tokens_ffd、max_samples >= 1 和 text_cache=offline")

    comfy_paths = None
    staging_root = None
    encoder_base_dir = None
    if mode == "comfyui_files":
        comfy_paths = {key: str(_absolute(config[key], runtime.project_root)) for key in comfy_required}
        sft_dit = str(config.get("sft_dit_path") or "").strip()
        if variant == "sft":
            comfy_paths["sft_dit_path"] = str(_absolute(sft_dit, runtime.project_root)) if sft_dit else comfy_paths["dit_path"]
        digest = comfy_layout_digest(comfy_paths, model=variant)
        staging_dir = _absolute(runtime.project_root / ".cache" / "kohaku-moss" / "comfy-layout" / digest, runtime.project_root)
        staging_root = str(staging_dir)
        dit_key = "sft_dit_path" if variant == "sft" else "dit_path"
        weights_dir = _resolve_comfy_weight_path(comfy_paths[dit_key], runtime.project_root)
        encoder_base_dir = staging_dir / "MOSS-Image-Base"
    else:
        raw_weights = _absolute(config["pretrained_model_name_or_path"], runtime.project_root)
        weights_dir, encoder_base_dir = _resolve_native_weights(raw_weights, variant)

    text_encode_cfg, vae_encode_cfg = _encode_settings(profile)

    values = {
        "WEIGHTS": str(weights_dir),
        "VARIANT": variant,
        "DATASETS": [{
            "source": "kohya",
            "path": str(_absolute(config["train_data_dir"], runtime.project_root)),
            "repeat_prefix": "first",
            "include_root": True,
            "txt_as": caption_mode,
        }],
        "CAPTION": (
            {"template": "tags", "shuffle": True, "keep": ()}
            if caption_mode == "tags"
            else {"template": "nl", "keep": ()}
        ),
        "OVERLONG": "drop_tokens",
        "OUTPUT_DIR": str(_absolute(config["output_dir"], runtime.project_root)),
        "RUN_NAME": name,
        "STEPS": steps,
        "BATCHING": batching,
        "BATCH_SIZE": _integer(config.get("batch_size", 4), "batch_size", 1),
        "MAX_TOKENS": _integer(config.get("max_tokens", 12288), "max_tokens", 256),
        "MAX_SAMPLES": max_samples,
        "GRAD_ACC": _integer(config.get("grad_acc", 1), "grad_acc", 1),
        "RESOLUTION_MODE": resolution_mode,
        "TARGET_AREA": _integer(config.get("target_area", 1024 * 1024), "target_area", 65536),
        "LATENT_CACHE": latent_cache,
        "TEXT_CACHE": text_cache,
        "CACHE_DTYPE": cache_dtype,
        "TEXT_ENCODE": text_encode_cfg,
        "ALGO": algorithm,
        "PRESET": preset,
        "DIM": dim,
        "ALPHA": alpha,
        "ALGO_KWARGS": _algo_kwargs(config, algorithm),
        "DORA": dora,
        "DORA_DETACH": _bool(config.get("network_dora_detach"), False),
        "TRAIN_NORMS": train_norms,
        "ADAPTER_MODE": adapter_mode,
        "LORAPLUS_RATIO": _float(config.get("loraplus_ratio", 1.0), "loraplus_ratio", 0.0),
        "DROPOUT": {
            "input": _float(config.get("dropout_input", 0.0), "dropout_input", 0.0),
            "rank": _float(config.get("dropout_rank", 0.0), "dropout_rank", 0.0),
            "module": _float(config.get("dropout_module", 0.0), "dropout_module", 0.0),
        },
        "OPTIMIZER": optimizer,
        "LR": float(config.get("learning_rate", 1e-4)),
        "WEIGHT_DECAY": _float(config.get("weight_decay", 0.01), "weight_decay", 0.0),
        "GRAD_CLIP": _float(config.get("grad_clip", 1.0), "grad_clip", 0.0),
        "EMA": _float(config.get("ema", 0.0), "ema", 0.0),
        "SCHEDULE": {
            "mode": schedule_mode,
            "warmup": warmup,
            "end": schedule_end,
            "min_value": _float(config.get("lr_min_value", 0.1), "lr_min_value", 0.0),
        },
        "MEMORY_PROFILE": profile,
        "PRECISION": precision,
        "BASE_PRECISION": base_precision,
        "COMPILE": compile_mode,
        "TUNE": tune_mode,
        "RETUNE_STEPS": _integer(config.get("retune_steps", 3), "retune_steps"),
        "PARALLEL": parallel,
        "DEVICES": devices,
        "SAVE_EVERY": _integer(config.get("save_every_n_steps", 500), "save_every_n_steps"),
        "SAVE_MINUTES": _integer(config.get("save_minutes", 0), "save_minutes"),
        "KEEP_LAST": _integer(config.get("keep_last", 3), "keep_last"),
        "SAMPLE_EVERY": sample_every,
        "SAMPLE_PROMPTS": prompts,
        "SAMPLE_NEGATIVE": str(config.get("sample_negative") or ""),
        "SAMPLE_STEPS": _integer(config.get("sample_steps", 50), "sample_steps", 1),
        "SAMPLE_CFG": _float(config.get("sample_cfg", 3.0), "sample_cfg", 0.0),
        "SAMPLE_SHIFT": _float(config.get("sample_shift", 5.0), "sample_shift", 0.0),
        "SAMPLE_SIZE": (
            _integer(config.get("sample_width", 1024), "sample_width", 256),
            _integer(config.get("sample_height", 1024), "sample_height", 256),
        ),
        "SAMPLE_SEEDS": (_integer(config.get("sample_seed", 0), "sample_seed"),),
        "SEED": _integer(config.get("seed", 0), "seed"),
        "LOG_EVERY": _integer(config.get("log_every", 10), "log_every", 1),
        "EXPORT_FORMATS": ("comfy", "lycoris"),
    }

    if profile == "minimal":
        values["MEMORY_OVERRIDES"] = {"pinned": False}
        values["PIN_MEMORY"] = False

    if precision in {"fp16", "auto"}:
        values["FP16_FIX"] = _choice(config.get("fp16_fix"), "fp16_fix", {"online", "fp32_residual", "none"}, "online")
        values["FP16_FIX_KWARGS"] = {"c": 1 / 16} if values["FP16_FIX"] == "online" else {}
    if parallel in {"pipeline", "threaded"}:
        schedules = {"auto", "gpipe", "async"} if parallel == "threaded" else {"auto", "gpipe", "1f1b"}
        schedule = _choice(config.get("pipeline_schedule"), "pipeline_schedule", schedules, "auto")
        values["PIPELINE_SCHEDULE"] = ("gpipe" if parallel == "threaded" else "1f1b") if schedule == "auto" else schedule
        values["MICROBATCHES"] = _integer(config.get("microbatches", 4), "microbatches", 1)
        if parallel == "pipeline":
            values["TOKEN_BUDGET"] = "exact"
            if values["MICROBATCHES"] < len(devices):
                raise ValueError("microbatches: pipeline 的微批次数不能少于 devices 数量")

    if vae_encode_cfg is not None:
        values["VAE_ENCODE"] = vae_encode_cfg

    if encoder_base_dir is not None:
        values["TEXT_ENCODER"] = str(encoder_base_dir)
        values["VAE"] = str(encoder_base_dir / "vae")

    cache_dir = str(config.get("cache_dir") or "").strip()
    if cache_dir:
        values["CACHE_DIR"] = str(_absolute(cache_dir, runtime.project_root))

    if base_precision in {"fp8", "fp8_compute", "mxfp8", "quant"}:
        values["FP8_RECIPE"] = _choice(config.get("fp8_recipe"), "fp8_recipe", {"row", "tensor", "block"}, "row")
        values["FP8_DGRAD"] = _choice(config.get("fp8_dgrad"), "fp8_dgrad", {"fp8", "16bit"}, "fp8")

    if not math.isfinite(values["LR"]) or values["LR"] <= 0:
        raise ValueError("learning_rate: 必须为正数")

    warnings = ["实验性高性能引擎；请先用小步数验证输出。"]
    if mode == "comfyui_files":
        warnings.append(
            "ComfyUI 单文件模式已启用：DiT 单文件由引擎直接零拷贝加载（自动兼容 Comfy-Org 融合 qkv 权重），"
            "Text Encoder / VAE / Tokenizer 自动通过零拷贝硬链挂载。"
        )
    if epochs:
        warnings.append("KohakuMossTrainer 原生以 STEPS 驱动；max_train_epochs 仅作 UI 备注。")
    if raw_sample_every > 0 and not prompts:
        warnings.append("已开启训练预览但未填写 sample_prompts，已自动跳过预览采样。")
    if values["DORA_DETACH"] and not dora:
        warnings.append("已勾选 network_dora_detach，但未启用 network_dora。")
    if tune_mode == "table" and sys.platform == "win32":
        warnings.append("若本机 MSVC 无法编译 triton-windows，请将 tune_mode 设为 off。")
    return AdaptedConfig(values, warnings, mode, comfy_paths, staging_root)


def dump_config(adapted, directory, run_id):
    path = Path(directory) / f"{run_id}-kohaku-moss.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '"""Generated by Next Trainer for the pinned KohakuMossTrainer runtime."""',
        *[f"{key} = {value!r}" for key, value in adapted.values.items()],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path.resolve()

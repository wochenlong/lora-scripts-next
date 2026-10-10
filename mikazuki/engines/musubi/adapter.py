from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import re
import sys

from .families import (
    DEFAULT_FAMILY,
    FAMILIES,
    family_for,
)
from .settings import RuntimeConfig


# Legacy alias for the pack's original Krea 2 module; family-aware code should
# read FamilySpec.network_module instead.
NETWORK_MODULE = FAMILIES[DEFAULT_FAMILY].network_module

UI_ONLY_FIELDS = {
    "model_train_type",
    "lora_type",
    "enable_preview",
    "positive_prompts",
    "negative_prompts",
    "sample_width",
    "sample_height",
    "sample_cfg",
    "sample_seed",
    "sample_steps",
    "sample_sampler",
    "sample_scheduler",
    "randomly_choice_prompt",
    "prompt_file",
    "enable_debug_options",
    "network_args_custom",
    "optimizer_args_custom",
    "ui_custom_params",
}

PATH_FIELDS = {
    "dit",
    "vae",
    "text_encoder",
    "turbo_dit",
    "unconditional_dit",
    "network_weights",
    "base_weights",
    "sample_prompts",
    "output_dir",
    "logging_dir",
}

SUPPORTED_FIELDS = {
    # model
    "dit",
    "vae",
    "text_encoder",
    "turbo_dit",
    "turbo_dit_cache",
    "fp8_base",
    "fp8_scaled",
    # ideogram4 (Ideogram 4): FP8-only base, optional asymmetric-CFG DiT and
    # caption / sampling controls.
    "unconditional_dit",
    "use_unconditional_dit_for_lora_sampling",
    "dit_dtype",
    "vae_dtype",
    "text_cache_dtype",
    "validate_caption_structure",
    "warn_on_caption_issues",
    "log_loss_stats",
    "sampler_preset",
    "initial_sigma",
    "ideogram4_timestep_mu",
    "ideogram4_timestep_std",
    # training
    "max_train_epochs",
    "max_train_steps",
    "seed",
    "mixed_precision",
    "gradient_checkpointing",
    "gradient_accumulation_steps",
    "max_data_loader_n_workers",
    "persistent_data_loader_workers",
    "learning_rate",
    "optimizer_type",
    "optimizer_args",
    "max_grad_norm",
    "lr_scheduler",
    "lr_warmup_steps",
    "lr_decay_steps",
    "lr_scheduler_num_cycles",
    "lr_scheduler_power",
    "lr_scheduler_min_lr_ratio",
    "lr_scheduler_args",
    "guidance_scale",
    "timestep_sampling",
    "discrete_flow_shift",
    "sigmoid_scale",
    "weighting_scheme",
    "logit_mean",
    "logit_std",
    "mode_scale",
    "min_timestep",
    "max_timestep",
    # memory / attention / compile
    "blocks_to_swap",
    "use_pinned_memory_for_block_swap",
    "block_swap_h2d_only",
    "img_in_txt_in_offloading",
    "disable_numpy_memmap",
    "sdpa",
    "flash_attn",
    "sage_attn",
    "xformers",
    "split_attn",
    "compile",
    "compile_backend",
    "compile_mode",
    "compile_dynamic",
    "compile_fullgraph",
    "compile_cache_size_limit",
    # network
    "network_module",
    "network_dim",
    "network_alpha",
    "network_dropout",
    "network_args",
    "network_weights",
    "dim_from_weights",
    "scale_weight_norms",
    "base_weights",
    "base_weights_multiplier",
    # save / load
    "output_dir",
    "output_name",
    "save_every_n_epochs",
    "save_every_n_steps",
    "save_last_n_epochs",
    "save_last_n_steps",
    "save_state",
    "save_state_on_train_end",
    "save_precision",
    "no_metadata",
    # logging
    "logging_dir",
    "log_with",
    "log_prefix",
    "log_tracker_name",
    "wandb_run_name",
    "wandb_api_key",
    # sampling
    "sample_prompts",
    "sample_every_n_steps",
    "sample_every_n_epochs",
    "sample_at_first",
    # huggingface
    "huggingface_repo_id",
    "huggingface_repo_type",
    "huggingface_path_in_repo",
    "huggingface_repo_visibility",
    "async_upload",
}

BOOL_FIELDS = {
    "turbo_dit_cache",
    "fp8_base",
    "fp8_scaled",
    "use_unconditional_dit_for_lora_sampling",
    "validate_caption_structure",
    "warn_on_caption_issues",
    "log_loss_stats",
    "gradient_checkpointing",
    "persistent_data_loader_workers",
    "use_pinned_memory_for_block_swap",
    "block_swap_h2d_only",
    "img_in_txt_in_offloading",
    "disable_numpy_memmap",
    "sdpa",
    "flash_attn",
    "sage_attn",
    "xformers",
    "split_attn",
    "compile",
    "compile_dynamic",
    "compile_fullgraph",
    "dim_from_weights",
    "save_state",
    "save_state_on_train_end",
    "no_metadata",
    "sample_at_first",
    "async_upload",
}

INT_FIELDS = {
    "max_train_epochs",
    "max_train_steps",
    "seed",
    "gradient_accumulation_steps",
    "max_data_loader_n_workers",
    "lr_warmup_steps",
    "lr_decay_steps",
    "lr_scheduler_num_cycles",
    "lr_scheduler_timescale",
    "min_timestep",
    "max_timestep",
    "blocks_to_swap",
    "compile_cache_size_limit",
    "network_dim",
    "sample_every_n_steps",
    "sample_every_n_epochs",
    "save_every_n_epochs",
    "save_every_n_steps",
    "save_last_n_epochs",
    "save_last_n_steps",
}

FLOAT_FIELDS = {
    "learning_rate",
    "max_grad_norm",
    "lr_scheduler_power",
    "lr_scheduler_min_lr_ratio",
    "guidance_scale",
    "discrete_flow_shift",
    "sigmoid_scale",
    "logit_mean",
    "logit_std",
    "mode_scale",
    "network_alpha",
    "network_dropout",
    "scale_weight_norms",
    "base_weights_multiplier",
    "initial_sigma",
    "ideogram4_timestep_mu",
    "ideogram4_timestep_std",
}

DATASET_GENERAL_KEYS = {"resolution", "caption_extension", "batch_size", "enable_bucket", "bucket_no_upscale"}

# Cache-stage flags: forwarded to the caching scripts as CLI flags, but never
# written into the train TOML (the train script only shares a subset of args).
CACHE_ONLY_FIELDS = {"vae_dtype", "text_cache_dtype"}

SUBSET_REPEAT_PATTERN = re.compile(r"^(\d+)_(.+)$")


@dataclass
class AdaptedConfig:
    values: dict[str, Any]
    dataset: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


class AdapterError(ValueError):
    pass


def is_empty(value: Any) -> bool:
    if value is None or value is False:
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "undefined", "null", "nan"}:
        return True
    return False


def truthy(value: Any) -> bool:
    return value in (True, "true", "True", "1", 1)


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def resolution_pair(value: Any, default: int = 1024) -> list[int]:
    if value is None:
        return [default, default]
    if isinstance(value, int):
        return [value, value]
    text = str(value).replace("x", ",").replace(" ", "")
    parts = [p for p in text.split(",") if p]
    if len(parts) == 1:
        size = int_value(parts[0], default)
        return [size, size]
    if len(parts) >= 2:
        return [int_value(parts[0], default), int_value(parts[1], default)]
    return [default, default]


def normalize_kv_args(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    key_index: dict[str, int] = {}
    for raw in values:
        if not isinstance(raw, str) or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or value.lower() in {"undefined", "null", "nan"}:
            continue
        item = f"{key}={value}"
        if key in key_index:
            out[key_index[key]] = item
        else:
            key_index[key] = len(out)
            out.append(item)
    return out


def _coerce_scalar(key: str, value: Any) -> Any:
    """GUI posts numbers as strings ("1e-4"); argparse --config_file parsing does
    not apply type= conversion to Namespace values, so coerce here."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if key in INT_FIELDS:
        try:
            return int(float(text))
        except ValueError:
            return value
    if key in FLOAT_FIELDS:
        try:
            return float(text)
        except ValueError:
            return value
    return value


def resolve_path(value: Any, base: Path) -> str:
    path = Path(str(value))
    if not path.is_absolute():
        path = base / path
    return path.resolve().as_posix()


def dataset_cache_slug(train_data_dir: Path, base: Path) -> str:
    resolved = train_data_dir if train_data_dir.is_absolute() else (base / train_data_dir).resolve()
    try:
        rel = resolved.relative_to(base.resolve())
        parts = [part for part in rel.parts if part not in (".", "..")]
        if parts:
            slug = "_".join(parts)
            return re.sub(r"[^\w.-]+", "_", slug) or "dataset"
    except ValueError:
        pass
    name = resolved.name or "dataset"
    return re.sub(r"[^\w.-]+", "_", name)


def discover_subsets(train_data_dir: Path) -> list[tuple[Path, int]]:
    """Kohya-style layout: subdirectories named `<repeats>_<name>`.

    Returns (image_directory, num_repeats) entries. Falls back to the
    directory itself with num_repeats=1 when no matching subdirectory exists.
    """
    entries: list[tuple[Path, int]] = []
    if train_data_dir.is_dir():
        for child in sorted(train_data_dir.iterdir()):
            if not child.is_dir():
                continue
            match = SUBSET_REPEAT_PATTERN.match(child.name)
            if match:
                entries.append((child, max(1, int(match.group(1)))))
    if not entries:
        entries.append((train_data_dir, 1))
    return entries


def build_dataset_config(source: dict[str, Any], runtime: RuntimeConfig) -> dict[str, Any]:
    train_data_dir = source.get("train_data_dir")
    if is_empty(train_data_dir):
        raise AdapterError("缺少训练数据集路径 (train_data_dir)")
    data_dir = Path(resolve_path(train_data_dir, runtime.lora_next_root))
    if not data_dir.is_dir():
        raise AdapterError(f"训练数据集路径不存在: {data_dir}")

    batch_size = int_value(source.get("train_batch_size") or source.get("batch_size"), 1) or 1
    general = {
        "resolution": resolution_pair(source.get("resolution")),
        "caption_extension": str(source.get("caption_extension") or ".txt"),
        "batch_size": batch_size,
        "enable_bucket": truthy(source.get("enable_bucket", True)),
        "bucket_no_upscale": truthy(source.get("bucket_no_upscale", False)),
    }

    slug = dataset_cache_slug(data_dir, runtime.lora_next_root)
    datasets: list[dict[str, Any]] = []
    for image_dir, num_repeats in discover_subsets(data_dir):
        cache_dir = (runtime.cache_dir / slug / image_dir.name).resolve()
        datasets.append(
            {
                "image_directory": image_dir.resolve().as_posix(),
                "cache_directory": cache_dir.as_posix(),
                "num_repeats": num_repeats,
            }
        )
    return {"general": general, "datasets": datasets}


def adapt_config(
    source: dict[str, Any],
    runtime: RuntimeConfig,
    run_id: str,
    family: str = DEFAULT_FAMILY,
) -> AdaptedConfig:
    spec = family_for(family)
    warnings: list[str] = []
    dataset = build_dataset_config(source, runtime)

    values: dict[str, Any] = {}
    custom_network_args = normalize_kv_args(source.get("network_args_custom"))
    custom_optimizer_args = normalize_kv_args(source.get("optimizer_args_custom"))

    for key, raw in source.items():
        if key in UI_ONLY_FIELDS or key in DATASET_GENERAL_KEYS:
            continue
        if key in {"train_data_dir", "train_batch_size", "batch_size", "dataset_repeats", "num_repeats", "reg_data_dir"}:
            continue
        if is_empty(raw):
            continue
        if key == "network_args":
            normalized = normalize_kv_args(raw)
            if normalized:
                values["network_args"] = normalized
            continue
        if key == "optimizer_args":
            normalized = normalize_kv_args(raw)
            if normalized:
                values["optimizer_args"] = normalized
            continue
        if key in PATH_FIELDS:
            values[key] = resolve_path(raw, runtime.lora_next_root)
            continue
        if key in BOOL_FIELDS:
            if truthy(raw):
                values[key] = True
            continue
        if key in SUPPORTED_FIELDS:
            values[key] = _coerce_scalar(key, raw)
            continue
        if key.startswith("_"):
            continue
        warnings.append(f"未知字段已忽略: {key}")

    if custom_network_args:
        values["network_args"] = normalize_kv_args([*values.get("network_args", []), *custom_network_args])
    if custom_optimizer_args:
        values["optimizer_args"] = normalize_kv_args([*values.get("optimizer_args", []), *custom_optimizer_args])

    for field_name, label in (
        ("dit", f"{spec.label} DiT 模型路径"),
        ("vae", "VAE 模型路径"),
        ("text_encoder", spec.text_encoder_label),
    ):
        if is_empty(values.get(field_name)):
            raise AdapterError(f"缺少 {label} ({field_name})")

    # Both trainers run bf16; fp16 is not supported by either.
    mixed = str(values.get("mixed_precision", "") or "").strip().lower()
    if mixed in {"", "none", "null"}:
        values["mixed_precision"] = "bf16"
    elif mixed == "fp16":
        values["mixed_precision"] = "bf16"
        warnings.append(f"{spec.label} 训练仅支持 bf16，已将 mixed_precision 从 fp16 改为 bf16")
    elif mixed != "bf16":
        raise AdapterError(f"mixed_precision={mixed} 不被 {spec.label} 支持，请使用 bf16")

    if spec.supports_fp8_pair:
        # Krea 2: fp8_base and fp8_scaled must be paired. Trainer asserts
        # ``fp8_scaled requires fp8_base``; plain fp8_base without scaled is also rejected.
        # Prefer both ON when either is requested (product default). Both OFF is allowed.
        fp8_base = bool(values.get("fp8_base"))
        fp8_scaled = bool(values.get("fp8_scaled"))
        if fp8_base or fp8_scaled:
            if not (fp8_base and fp8_scaled):
                values["fp8_base"] = True
                values["fp8_scaled"] = True
                warnings.append("Krea 2 的 fp8 须同时开启 fp8_base 与 fp8_scaled，已自动成对开启")
    else:
        # Ideogram 4's base is always FP8; upstream takes no --fp8_base/--fp8_scaled.
        dropped = [key for key in ("fp8_base", "fp8_scaled") if values.pop(key, None) is not None]
        if dropped:
            warnings.append(f"{spec.label} 基底固定为 FP8，无需 {'/'.join(dropped)}，已移除")

    if spec.supports_turbo_dit:
        # RAW-train / Turbo-sample constraints (see musubi krea2_train_network.py).
        if not is_empty(values.get("turbo_dit")):
            if int_value(values.get("blocks_to_swap")) > 0:
                raise AdapterError(
                    "turbo_dit 与 blocks_to_swap 互斥：block swap 的 offloader 会绕过外部权重切换，"
                    "导致 RAW/Turbo 权重混合。请关闭 blocks_to_swap，或去掉 turbo_dit 改用 RAW 采样"
                )
            if is_empty(values.get("sample_prompts")):
                warnings.append("已设置 turbo_dit 但未配置 sample_prompts；Turbo 仅用于训练中采样预览")
        elif values.get("turbo_dit_cache"):
            raise AdapterError("turbo_dit_cache 需要同时设置 turbo_dit（Turbo DiT 模型路径）")
    else:
        for key in ("turbo_dit", "turbo_dit_cache"):
            if values.pop(key, None) is not None:
                warnings.append(f"{spec.label} 不支持 Krea 2 的 {key}，已忽略")

    if spec.blocks_to_swap_max and int_value(values.get("blocks_to_swap")) > spec.blocks_to_swap_max:
        raise AdapterError(
            f"blocks_to_swap={int_value(values.get('blocks_to_swap'))} 超出 {spec.label} 上限 "
            f"{spec.blocks_to_swap_max}"
        )

    if not spec.supports_fp8_pair:
        # Ideogram 4 uses plain MSE flow matching; upstream rejects other schemes.
        scheme = str(values.get("weighting_scheme", "") or "").strip()
        if scheme and scheme != "none":
            values.pop("weighting_scheme", None)
            warnings.append(f"{spec.label} 仅支持 weighting_scheme=none，已忽略 {scheme}")
        # Asymmetric CFG is inference-only unless explicitly opted in for LoRA sampling.
        unconditional = values.get("unconditional_dit")
        opt_in = bool(values.get("use_unconditional_dit_for_lora_sampling"))
        if opt_in and is_empty(unconditional):
            raise AdapterError(
                "use_unconditional_dit_for_lora_sampling 需要同时设置 unconditional_dit（unconditional DiT 路径）"
            )
        if not opt_in and not is_empty(unconditional):
            warnings.append(
                f"{spec.label} 训练中采样默认只用 conditional DiT；unconditional_dit 需与 "
                "use_unconditional_dit_for_lora_sampling 同时开启才会用于训练采样"
            )

    # torch.compile needs Triton, which is unavailable on Windows.
    if sys.platform == "win32" and values.get("compile"):
        values.pop("compile", None)
        for key in ("compile_backend", "compile_mode", "compile_dynamic", "compile_fullgraph", "compile_cache_size_limit"):
            values.pop(key, None)
        warnings.append("compile 在 Windows 上不可用（依赖仅限 Linux 的 Triton），已自动关闭")

    values["network_module"] = spec.network_module
    if not is_empty(source.get("network_module")) and source["network_module"] != spec.network_module:
        warnings.append(f"network_module={source['network_module']} 已替换为 {spec.network_module}")

    values.setdefault("network_dim", spec.default_network_dim)
    values.setdefault("network_alpha", spec.default_network_alpha)
    values.setdefault("log_with", "tensorboard")

    if not is_empty(values.get("sample_prompts")):
        for key, default in spec.sampler_defaults.items():
            if is_empty(values.get(key)):
                values[key] = default

    output_dir = source.get("output_dir")
    values["output_dir"] = resolve_path(output_dir, runtime.lora_next_root) if not is_empty(output_dir) else runtime.output_dir.as_posix()
    logging_dir = source.get("logging_dir")
    values["logging_dir"] = (
        resolve_path(logging_dir, runtime.lora_next_root)
        if not is_empty(logging_dir)
        else (runtime.logging_dir / run_id).as_posix()
    )
    values.setdefault("output_name", run_id)

    return AdaptedConfig(values=values, dataset=dataset, warnings=warnings)


def toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_scalar(item) for item in value) + "]"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def dump_train_toml(values: dict[str, Any]) -> str:
    return "".join(
        f"{key} = {toml_scalar(value)}\n"
        for key, value in values.items()
        if key not in CACHE_ONLY_FIELDS
    )


def dump_dataset_toml(dataset: dict[str, Any]) -> str:
    lines = ["[general]\n"]
    lines.extend(f"{key} = {toml_scalar(value)}\n" for key, value in dataset["general"].items())
    for entry in dataset["datasets"]:
        lines.append("\n[[datasets]]\n")
        lines.extend(f"{key} = {toml_scalar(value)}\n" for key, value in entry.items())
    return "".join(lines)

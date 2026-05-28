from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import Any


SUPPORTED_FIELDS = {
    "pretrained_model_name_or_path",
    "vae",
    "qwen3",
    "llm_adapter_path",
    "t5_tokenizer_path",
    "resume",
    "qwen3_max_token_length",
    "t5_max_token_length",
    "timestep_sampling",
    "sigmoid_scale",
    "discrete_flow_shift",
    "weighting_scheme",
    "logit_mean",
    "logit_std",
    "mode_scale",
    "attn_mode",
    "split_attn",
    "vae_chunk_size",
    "vae_disable_cache",
    "unsloth_offload_checkpointing",
    "train_data_dir",
    "reg_data_dir",
    "resolution",
    "enable_bucket",
    "min_bucket_reso",
    "max_bucket_reso",
    "bucket_reso_steps",
    "output_dir",
    "output_name",
    "save_model_as",
    "save_precision",
    "save_every_n_epochs",
    "save_every_n_steps",
    "max_train_epochs",
    "max_train_steps",
    "train_batch_size",
    "gradient_checkpointing",
    "gradient_accumulation_steps",
    "network_train_unet_only",
    "network_train_text_encoder_only",
    "learning_rate",
    "unet_lr",
    "text_encoder_lr",
    "optimizer_type",
    "optimizer_args",
    "lr_scheduler",
    "lr_warmup_steps",
    "network_module",
    "network_weights",
    "network_dim",
    "network_alpha",
    "network_dropout",
    "network_args",
    "dim_from_weights",
    "scale_weight_norms",
    "train_norm",
    "full_matrix",
    "pissa_init",
    "pissa_method",
    "pissa_niter",
    "pissa_oversample",
    "pissa_apply_conv2d",
    "pissa_export_mode",
    "sample_prompts",
    "sample_at_first",
    "sample_every_n_epochs",
    "caption_extension",
    "shuffle_caption",
    "keep_tokens",
    "caption_tag_dropout_rate",
    "prefer_json_caption",
    "noise_offset",
    "multires_noise_iterations",
    "multires_noise_discount",
    "fp8_base",
    "fp8_base_unet",
    "cache_latents",
    "cache_latents_to_disk",
    "cache_text_encoder_outputs",
    "cache_text_encoder_outputs_to_disk",
    "persistent_data_loader_workers",
    "max_data_loader_n_workers",
    "text_encoder_batch_size",
    "disable_mmap_load_safetensors",
    "blocks_to_swap",
    "cpu_offload_checkpointing",
    "mixed_precision",
    "full_fp16",
    "full_bf16",
    "seed",
    "logging_dir",
    "log_with",
    "self_attn_lr",
    "cross_attn_lr",
    "mlp_lr",
    "mod_lr",
    "llm_adapter_lr",
}

NETWORK_ONLY_FIELDS = {
    "network_module",
    "network_weights",
    "network_dim",
    "network_alpha",
    "network_dropout",
    "network_args",
    "dim_from_weights",
    "scale_weight_norms",
    "train_norm",
    "full_matrix",
    "pissa_init",
    "pissa_method",
    "pissa_niter",
    "pissa_oversample",
    "pissa_apply_conv2d",
    "pissa_export_mode",
    "conv_dim",
    "conv_alpha",
    "lycoris_algo",
    "lokr_factor",
    "use_cp",
    "use_scalar",
    "decompose_both",
    "bypass_mode",
    "dora_wd",
    "rank_dropout",
    "module_dropout",
    "rank_dropout_scale",
    "dropout",
    "tlora_min_rank",
    "tlora_rank_schedule",
    "tlora_orthogonal_init",
    "network_train_unet_only",
    "network_train_text_encoder_only",
    "enable_base_weight",
    "base_weights",
    "base_weights_multiplier",
}

UI_ONLY_FIELDS = {
    "model_train_type",
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
    "json_caption_hint",
    "lora_type",
}

# Top-level UI fields that should be injected into network_args for T-LoRA.
TLORA_NETWORK_ARG_FIELDS = {
    "tlora_min_rank",
    "tlora_rank_schedule",
    "tlora_orthogonal_init",
}

# LyCORIS UI fields → network_args key names.  sd-scripts only forwards
# network_args items to lycoris.kohya.create_network(**kwargs); top-level
# TOML keys are silently ignored.  Map UI field → LyCORIS kwarg name.
LYCORIS_NETWORK_ARG_MAP: dict[str, str] = {
    "lycoris_algo": "algo",
    "lokr_factor": "factor",
    "conv_dim": "conv_dim",
    "conv_alpha": "conv_alpha",
    "use_cp": "use_cp",
    "use_scalar": "use_scalar",
    "decompose_both": "decompose_both",
    "bypass_mode": "bypass_mode",
    "dora_wd": "dora_wd",
    "full_matrix": "full_matrix",
    "rank_dropout": "rank_dropout",
    "module_dropout": "module_dropout",
    "rank_dropout_scale": "rank_dropout_scale",
    "train_norm": "train_norm",
    "dropout": "dropout",
}


def _is_empty_value(value: Any) -> bool:
    """Check if a value is empty/invalid (None, NaN, 'undefined', 'null', '')."""
    if value is None or value is False:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "undefined", "null", "nan"}:
        return True
    return False


def _normalize_network_args(values: Any) -> list[str]:
    """
    Normalize network_args from UI payload:
    - keep string items only
    - drop empty / malformed items
    - drop `key=undefined` and `key=null`
    - for duplicate keys, keep the last value (so custom args override earlier defaults)
    """
    if not isinstance(values, list):
        return []

    ordered: list[str] = []
    key_index: dict[str, int] = {}

    for raw in values:
        if not isinstance(raw, str):
            continue
        item = raw.strip()
        if not item or "=" not in item:
            continue

        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value.lower() in {"undefined", "null", "nan"}:
            continue

        normalized = f"{key}={value}"
        if key in key_index:
            ordered[key_index[key]] = normalized
        else:
            key_index[key] = len(ordered)
            ordered.append(normalized)

    return ordered


def adapt_anima_config(
    config: dict[str, Any], *, finetune: bool = False
) -> tuple[dict[str, Any], list[str]]:
    source = deepcopy(config)
    adapted: dict[str, Any] = {}
    warnings: list[str] = []

    if finetune:
        for key in list(source):
            if key in NETWORK_ONLY_FIELDS:
                source.pop(key, None)
        source.pop("network_args_custom", None)
        source.pop("lora_type", None)

    custom_network_args = source.pop("network_args_custom", None)
    if not finetune:
        merged_network_args: list[str] = []
        if isinstance(source.get("network_args"), list):
            merged_network_args.extend(source["network_args"])
        if isinstance(custom_network_args, list):
            merged_network_args.extend(custom_network_args)
        normalized_network_args = _normalize_network_args(merged_network_args)
        if normalized_network_args:
            source["network_args"] = normalized_network_args
        elif "network_args" in source:
            source.pop("network_args", None)

    # LyCORIS default preset does not include Anima module class names, which may
    # produce zero trainable modules for LoKr. Inject Anima-specific preset unless
    # user already provided one via network_args.
    if not finetune and source.get("network_module") == "lycoris.kohya":
        network_args = source.get("network_args")
        has_preset = isinstance(network_args, list) and any(
            isinstance(item, str) and item.strip().startswith("preset=")
            for item in network_args
        )
        if not has_preset:
            preset_path = (
                Path(__file__).resolve().parents[2] / "config" / "lycoris_anima_preset.toml"
            )
            source["network_args"] = list(network_args or []) + [
                f"preset={preset_path.as_posix()}"
            ]

    # LyCORIS: convert top-level UI fields into network_args.  sd-scripts only
    # passes network_args items (as **kwargs) to lycoris.kohya.create_network();
    # top-level TOML keys like use_cp, decompose_both, etc. are silently lost.
    if not finetune and source.get("network_module") == "lycoris.kohya":
        network_args = list(source.get("network_args") or [])
        for ui_field, arg_key in LYCORIS_NETWORK_ARG_MAP.items():
            value = source.pop(ui_field, None)
            if _is_empty_value(value):
                continue
            network_args.append(f"{arg_key}={value}")
        if network_args:
            source["network_args"] = network_args

    # T-LoRA: convert top-level UI fields into network_args so sd-scripts
    # can forward them to create_network() as **kwargs.
    if not finetune and source.get("network_module") == "networks.tlora_anima":
        network_args = list(source.get("network_args") or [])
        for field in TLORA_NETWORK_ARG_FIELDS:
            value = source.pop(field, None)
            if not _is_empty_value(value):
                network_args.append(f"{field}={value}")
        if network_args:
            source["network_args"] = network_args

    for key, value in source.items():
        if key in UI_ONLY_FIELDS or key in TLORA_NETWORK_ARG_FIELDS or key in LYCORIS_NETWORK_ARG_MAP:
            continue
        if _is_empty_value(value):
            continue
        if key in SUPPORTED_FIELDS:
            if key == "attn_mode" and value in ("", None):
                continue
            adapted[key] = value
            continue
        if key.startswith("anima_"):
            warnings.append(f"Unsupported Anima field ignored: {key}")
            continue
        warnings.append(f"Unknown field passed through to sd-scripts: {key}")
        adapted[key] = value

    return adapted, warnings

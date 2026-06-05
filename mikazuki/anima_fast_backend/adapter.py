from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .settings import RuntimeConfig


UI_ONLY_FIELDS = {
    "model_train_type",
    "anima_backend",
    "anima_fast_root",
    "anima_fast_python",
    "anima_fast_preflight_level",
    "anima_fast_dataset_mode",
    "anima_fast_run_preprocess",
    "anima_fast_allow_unsupported",
    "enable_preview",
    "positive_prompts",
    "negative_prompts",
    "sample_width",
    "sample_height",
    "sample_cfg",
    "sample_seed",
    "sample_steps",
    "randomly_choice_prompt",
    "prompt_file",
    "sample_scheduler",
    "sample_sampler",
}

PATH_FIELDS = {
    "pretrained_model_name_or_path",
    "vae",
    "qwen3",
    "llm_adapter_path",
    "t5_tokenizer_path",
    "network_weights",
    "resume",
    "sample_prompts",
    "source_image_dir",
    "resized_image_dir",
    "lora_cache_dir",
    "output_dir",
    "logging_dir",
}

SUPPORTED_LORA_TYPES = {"lora"}
UNSUPPORTED_FAST_MEMORY_FIELDS = {
    "blocks_to_swap",
    "cpu_offload_checkpointing",
    "unsloth_offload_checkpointing",
}
FAST_NETWORK_ARGS_ALLOWLIST = {
    "rank_dropout",
    "module_dropout",
    "loraplus_lr_ratio",
    "loraplus_unet_lr_ratio",
    "loraplus_text_encoder_lr_ratio",
}

FAST_SUPPORTED_OPTIMIZERS = {
    "AdamW",
    "AdamW8bit",
    "PagedAdamW8bit",
    "RAdamScheduleFree",
    "Lion",
    "Lion8bit",
    "PagedLion8bit",
    "SGDNesterov",
    "SGDNesterov8bit",
    "DAdaptation",
    "DAdaptAdam",
    "DAdaptAdaGrad",
    "DAdaptAdanIP",
    "DAdaptLion",
    "DAdaptSGD",
    "AdaFactor",
    "Prodigy",
    "pytorch_optimizer.CAME",
}


@dataclass
class AdaptedConfig:
    values: dict[str, Any]
    warnings: list[str]


class AdapterError(ValueError):
    pass


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in {"", "undefined", "null", "nan"})


def truthy(value: Any) -> bool:
    return value in (True, "true", "True", "1", 1)


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def resolution_tokens(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        width = height = value
    else:
        text = str(value).replace("x", ",").replace(" ", "")
        parts = [p for p in text.split(",") if p]
        if len(parts) == 1:
            width = height = int_value(parts[0])
        elif len(parts) >= 2:
            width = int_value(parts[0])
            height = int_value(parts[1])
        else:
            return 0
    if width <= 0 or height <= 0:
        return 0
    return (width // 16) * (height // 16)


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


def normalize_fast_network_args(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    key_index: dict[str, int] = {}
    unsupported: list[str] = []
    malformed: list[str] = []
    for raw in values:
        if not isinstance(raw, str) or "=" not in raw:
            if raw not in (None, ""):
                malformed.append(str(raw))
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or value.lower() in {"undefined", "null", "nan"}:
            malformed.append(str(raw))
            continue
        if key not in FAST_NETWORK_ARGS_ALLOWLIST:
            unsupported.append(key)
            continue
        item = f"{key}={value}"
        if key in key_index:
            out[key_index[key]] = item
        else:
            key_index[key] = len(out)
            out.append(item)

    if malformed:
        raise AdapterError(
            "network_args_custom must be key=value lines; invalid item(s): "
            + ", ".join(malformed[:5])
        )
    if unsupported:
        allowed = ", ".join(sorted(FAST_NETWORK_ARGS_ALLOWLIST))
        raise AdapterError(
            "network_args_custom contains unsupported Anima Fast key(s): "
            + ", ".join(sorted(set(unsupported)))
            + f". Allowed keys: {allowed}"
        )
    return out


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


def default_dataset_cache_dir(
    source_dir: str | None,
    runtime: RuntimeConfig,
    run_id: str,
    subdir: str,
) -> Path:
    if source_dir and not is_empty(source_dir):
        path = Path(str(source_dir))
        if not path.is_absolute():
            path = (runtime.lora_next_root / path).resolve()
        else:
            path = path.resolve()
        return runtime.cache_dir / dataset_cache_slug(path, runtime.lora_next_root) / subdir
    return runtime.cache_dir / run_id / subdir


def adapt_config(source: dict[str, Any], runtime: RuntimeConfig, run_id: str) -> AdaptedConfig:
    warnings: list[str] = []
    lora_type = str(source.get("lora_type", "lora")).lower()
    if lora_type not in SUPPORTED_LORA_TYPES:
        raise AdapterError(f"lora_type={lora_type} is not supported by anima-lora-fast MVP")

    output_dir = source.get("output_dir") or runtime.output_dir
    logging_dir = source.get("logging_dir") or (runtime.logging_dir / run_id)
    source_dir = source.get("source_image_dir") or source.get("train_data_dir")

    values: dict[str, Any] = {
        "base_config": (runtime.anima_root / "configs" / "base.toml").resolve().as_posix(),
        "method": "lora",
        "methods_subdir": "gui-methods",
        "progress_jsonl": (runtime.logging_dir / f"{run_id}.progress.jsonl").resolve().as_posix(),
        "output_dir": resolve_path(output_dir, runtime.lora_next_root),
        "logging_dir": resolve_path(logging_dir, runtime.lora_next_root),
        "lora_cache_dir": resolve_path(
            source.get("lora_cache_dir") or default_dataset_cache_dir(str(source_dir) if source_dir else None, runtime, run_id, "lora"),
            runtime.lora_next_root,
        ),
        "resized_image_dir": resolve_path(
            source.get("resized_image_dir") or default_dataset_cache_dir(str(source_dir) if source_dir else None, runtime, run_id, "resized"),
            runtime.lora_next_root,
        ),
    }
    if source_dir:
        values["source_image_dir"] = resolve_path(source_dir, runtime.lora_next_root)

    for key, value in source.items():
        if key in UI_ONLY_FIELDS:
            continue
        if key in UNSUPPORTED_FAST_MEMORY_FIELDS:
            if (key == "blocks_to_swap" and int_value(value) > 0) or (key != "blocks_to_swap" and truthy(value)):
                warnings.append(f"{key} is not exposed in Anima Fast MVP and was ignored")
            continue
        if is_empty(value):
            continue
        if key in {"network_args", "network_args_custom"}:
            normalized = normalize_fast_network_args(value)
            target = "network_args"
            if normalized:
                existing = values.get(target, [])
                values[target] = normalize_fast_network_args([*existing, *normalized]) if existing else normalized
            continue
        if key in {"optimizer_args", "optimizer_args_custom"}:
            normalized = normalize_kv_args(value)
            target = "optimizer_args"
            if normalized:
                existing = values.get(target, [])
                values[target] = normalize_kv_args([*existing, *normalized]) if existing else normalized
            continue
        if key in PATH_FIELDS:
            values[key] = resolve_path(value, runtime.lora_next_root)
            continue
        if key in {"train_data_dir", "lora_type"}:
            continue
        values[key] = value

    values.setdefault("torch_compile", True)
    values.setdefault("static_token_count", 4096)
    if truthy(values.get("torch_compile")):
        tokens = resolution_tokens(values.get("resolution"))
        static_token_count = int_value(values.get("static_token_count"), 0)
        if tokens and tokens > static_token_count:
            values["static_token_count"] = tokens
            warnings.append(
                f"static_token_count 已按 resolution 自动提高到 {tokens}；"
                "高分辨率 Fast compile 会显著增加显存占用"
            )
    cache_keys = ("cache_latents", "cache_text_encoder_outputs")
    if truthy(values.get("skip_cache_check")) and any(truthy(values.get(key)) for key in cache_keys):
        for key in (*cache_keys, "skip_cache_check"):
            values[key] = False
        warnings.append(
            "cache_latents/cache_text_encoder_outputs 不能与 skip_cache_check 同时开启；"
            "已自动关闭缓存读取和跳过检查，改用 live encoding"
        )
    values.setdefault("compile_mode", "blocks")
    if str(values.get("compile_mode", "blocks")) == "full" and truthy(values.get("gradient_checkpointing")):
        values["compile_mode"] = "blocks"
        warnings.append("compile_mode=full 与 gradient_checkpointing 不兼容，已自动改为 blocks")
    values.setdefault("dynamo_backend", "inductor")
    if is_empty(values.get("attn_mode")):
        values["attn_mode"] = "torch"
        warnings.append("attn_mode 留空时使用 torch 保底；如需 flash 请先确认插件环境已安装 flash-attn")
    values.setdefault("network_module", "networks.lora_anima")

    if not is_empty(source.get("max_train_epochs")) and not is_empty(source.get("max_train_steps")):
        warnings.append("max_train_epochs is set; anima_lora derives max_train_steps from epochs and dataloader length")

    if source.get("network_module") and source["network_module"] != "networks.lora_anima":
        warnings.append(f"network_module={source['network_module']} was replaced by networks.lora_anima")
        values["network_module"] = "networks.lora_anima"

    optimizer_type = str(values.get("optimizer_type", source.get("optimizer_type", "AdamW8bit"))).strip()
    if optimizer_type and optimizer_type not in FAST_SUPPORTED_OPTIMIZERS:
        if optimizer_type == "Automagic":
            raise AdapterError(
                "optimizer_type=Automagic is not supported by the Anima Fast plugin runtime; "
                "choose AdamW8bit or another Fast optimizer"
            )
        raise AdapterError(
            f"optimizer_type={optimizer_type} is not supported by anima-lora-fast; "
            f"choose one of: {', '.join(sorted(FAST_SUPPORTED_OPTIMIZERS))}"
        )

    return AdaptedConfig(values=values, warnings=warnings)


def toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_scalar(item) for item in value) + "]"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def dump_flat_toml(values: dict[str, Any]) -> str:
    return "".join(f"{key} = {toml_scalar(value)}\n" for key, value in values.items())

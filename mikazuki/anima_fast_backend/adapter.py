from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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


@dataclass
class AdaptedConfig:
    values: dict[str, Any]
    warnings: list[str]


class AdapterError(ValueError):
    pass


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in {"", "undefined", "null", "nan"})


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


def resolve_path(value: Any, base: Path) -> str:
    path = Path(str(value))
    if not path.is_absolute():
        path = base / path
    return path.resolve().as_posix()


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
        "lora_cache_dir": resolve_path(source.get("lora_cache_dir") or (runtime.cache_dir / run_id / "lora"), runtime.lora_next_root),
        "resized_image_dir": resolve_path(source.get("resized_image_dir") or (runtime.cache_dir / run_id / "resized"), runtime.lora_next_root),
    }
    if source_dir:
        values["source_image_dir"] = resolve_path(source_dir, runtime.lora_next_root)

    for key, value in source.items():
        if key in UI_ONLY_FIELDS:
            continue
        if is_empty(value):
            continue
        if key in {"network_args", "optimizer_args", "network_args_custom", "optimizer_args_custom"}:
            normalized = normalize_kv_args(value)
            target = key.replace("_custom", "")
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
    values.setdefault("compile_mode", "blocks")
    values.setdefault("dynamo_backend", "inductor")
    values.setdefault("attn_mode", "flash")
    values.setdefault("network_module", "networks.lora_anima")

    if not is_empty(source.get("max_train_epochs")) and not is_empty(source.get("max_train_steps")):
        warnings.append("max_train_epochs is set; anima_lora derives max_train_steps from epochs and dataloader length")

    if source.get("network_module") and source["network_module"] != "networks.lora_anima":
        warnings.append(f"network_module={source['network_module']} was replaced by networks.lora_anima")
        values["network_module"] = "networks.lora_anima"

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

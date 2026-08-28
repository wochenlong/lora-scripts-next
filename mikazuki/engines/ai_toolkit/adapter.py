"""UI (kohya-dialect) config -> AI Toolkit native YAML tree.

Whitelist mapping per ADAPTATION_GUIDE step 4 and the #300 glossary
(docs/design/training-param-glossary.md): display stays unified, the adapter
writes engine-native keys. Semantically non-equivalent params (epoch vs steps,
single resolution vs resolution[]) are never silently merged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import re

import yaml

from .settings import RuntimeConfig


VARIANTS = {
    "klein-4b": {
        "arch": "flux2_klein_4b",
        "dit_filename": "flux-2-klein-base-4b.safetensors",
        "default_name_or_path": "black-forest-labs/FLUX.2-klein-base-4B",
        "text_encoder": "Qwen/Qwen3-4B",
        "te_hidden_size": 2560,
    },
    "klein-9b": {
        "arch": "flux2_klein_9b",
        "dit_filename": "flux-2-klein-base-9b.safetensors",
        "default_name_or_path": "black-forest-labs/FLUX.2-klein-base-9B",
        "text_encoder": "Qwen/Qwen3-8B",
        "te_hidden_size": 4096,
    },
}

UI_ONLY_FIELDS = {
    "model_train_type",
    "lora_type",
    "enable_preview",
    "prompt_file",
    "randomly_choice_prompt",
    "enable_debug_options",
    "network_args_custom",
    "optimizer_args_custom",
    "ui_custom_params",
}

# kohya-dialect optimizer labels -> toolkit native values
OPTIMIZER_MAP = {
    "adamw": "adamw",
    "adamw8bit": "adamw8bit",
    "adamw_torch": "adamw",
    "adafactor": "adafactor",
    "prodigy": "prodigy",
}

SAVE_DTYPE_MAP = {
    "bf16": "bf16",
    "fp16": "float16",
    "float": "float32",
    "float32": "float32",
    "float16": "float16",
}


@dataclass
class AdaptedConfig:
    config: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    # Local TE dir; upstream has no config key, so it travels via the launch
    # driver's AI_TOOLKIT_TE_PATH env instead of the yaml.
    te_path: str = ""


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


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def resolve_path(value: Any, base: Path) -> str:
    path = Path(str(value))
    if not path.is_absolute():
        path = base / path
    return path.resolve().as_posix()


def _resolution_list(value: Any, default: int = 1024) -> list[int]:
    """kohya single resolution ("1024" / "1024,1024" / "1024x768") -> toolkit
    resolution array. Non-square input collapses to the long side; buckets do
    the rest upstream. Never fabricates a multi-resolution list."""
    if value is None:
        return [default]
    if isinstance(value, int):
        return [value]
    text = str(value).replace("x", ",").replace(" ", "")
    parts = [p for p in text.split(",") if p]
    if not parts:
        return [default]
    return [max(int_value(p, default) for p in parts)]


def _sample_prompt_lines(value: Any) -> list[str]:
    """sample_prompts is a prompt-file path (one prompt per line, kohya style);
    toolkit wants an inline list."""
    if is_empty(value):
        return []
    path = Path(str(value))
    if not path.is_file():
        return []
    lines = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        # strip kohya sample-prompt option suffixes ("--n ..." etc.)
        line = re.split(r"\s--[a-zA-Z]", raw, maxsplit=1)[0].strip()
        if line:
            lines.append(line)
    return lines


def _map_optimizer(value: Any, warnings: list[str]) -> str:
    text = str(value or "adamw8bit").strip()
    mapped = OPTIMIZER_MAP.get(text.lower())
    if mapped is None:
        warnings.append(f"optimizer_type={text} 不在 AI Toolkit 已知优化器列表，按原样透传")
        return text
    return mapped


def adapt_config(source: dict[str, Any], runtime: RuntimeConfig, run_id: str, variant: str) -> AdaptedConfig:
    if variant not in VARIANTS:
        raise AdapterError(f"未知 AI Toolkit 变体: {variant!r}（支持: {', '.join(sorted(VARIANTS))}）")
    spec = VARIANTS[variant]
    warnings: list[str] = []

    train_data_dir = source.get("train_data_dir")
    if is_empty(train_data_dir):
        raise AdapterError("缺少训练数据集路径 (train_data_dir)")
    data_dir = Path(resolve_path(train_data_dir, runtime.lora_next_root))
    if not data_dir.is_dir():
        raise AdapterError(f"训练数据集路径不存在: {data_dir}")

    dit_raw = source.get("dit") or source.get("pretrained_model_name_or_path")
    if is_empty(dit_raw):
        raise AdapterError("缺少 Klein DiT 路径 (dit)：模型目录或 HF repo")
    dit_text = str(dit_raw).strip()
    dit_path = Path(dit_text)
    if not dit_path.is_absolute():
        dit_path = (runtime.lora_next_root / dit_path).resolve()
    if dit_path.is_file():
        # Toolkit wants the containing folder (or HF repo); a direct file works
        # when the filename matches the variant's expected DiT filename.
        if dit_path.name != spec["dit_filename"]:
            warnings.append(
                f"DiT 文件名 {dit_path.name} 与变体期望的 {spec['dit_filename']} 不一致，上游加载可能失败"
            )
        name_or_path = dit_path.parent.resolve().as_posix()
    elif dit_path.is_dir():
        name_or_path = dit_path.resolve().as_posix()
    else:
        # not a local path: treat as HF repo id, download happens upstream
        name_or_path = dit_text

    te_raw = source.get("text_encoder")
    if is_empty(te_raw):
        raise AdapterError(
            f"缺少文本编码器路径 (text_encoder)：Klein {variant} 需要本地 Qwen3 目录，"
            "请在「训练用模型」区探测并下载"
        )
    te_path = Path(resolve_path(te_raw, runtime.lora_next_root))
    if not te_path.is_dir():
        raise AdapterError(f"文本编码器目录不存在: {te_path}（可在「训练用模型」区下载）")

    steps = int_value(source.get("max_train_steps"), 0)
    if steps <= 0:
        if not is_empty(source.get("max_train_steps")):
            raise AdapterError("max_train_steps 必须为正整数")
        if not is_empty(source.get("max_train_epochs")):
            raise AdapterError(
                "AI Toolkit 只支持按步数 (max_train_steps) 训练，不支持 epoch；"
                "请换算后填写 max_train_steps"
            )
        raise AdapterError("缺少 max_train_steps（AI Toolkit 以步数计，无 epoch 概念）")
    if not is_empty(source.get("max_train_epochs")):
        warnings.append("max_train_epochs 对 AI Toolkit 无效（无 epoch 概念），已忽略，以 max_train_steps 为准")

    output_dir = source.get("output_dir")
    training_folder = (
        resolve_path(output_dir, runtime.lora_next_root) if not is_empty(output_dir) else runtime.output_dir.as_posix()
    )
    output_name = str(source.get("output_name") or "").strip() or run_id

    logging_dir_raw = source.get("logging_dir")
    log_dir = (
        resolve_path(logging_dir_raw, runtime.lora_next_root)
        if not is_empty(logging_dir_raw)
        else runtime.logging_dir.as_posix()
    )
    # Upstream logs TB scalars every `logging.log_every` steps (default 100),
    # which leaves short smoke runs with zero points.
    log_every = max(1, min(100, steps // 100))

    dataset: dict[str, Any] = {
        "folder_path": data_dir.resolve().as_posix(),
        "caption_ext": str(source.get("caption_extension") or ".txt").lstrip("."),
        "cache_latents_to_disk": True,
        "resolution": _resolution_list(source.get("resolution")),
    }
    if not is_empty(source.get("caption_dropout_rate")):
        dataset["caption_dropout_rate"] = float_value(source.get("caption_dropout_rate"))
    if truthy(source.get("shuffle_caption")):
        dataset["shuffle_tokens"] = True
    if not is_empty(source.get("dataset_repeats")):
        dataset["num_repeats"] = max(1, int_value(source.get("dataset_repeats"), 1))

    # Image-edit contract (image-edit-dataset-contract.md): control_data_dirs[]
    # pairs with train_data_dir by filename; toolkit consumes it as control_path list.
    control_dirs = source.get("control_data_dirs")
    if isinstance(control_dirs, str):
        control_dirs = [part.strip() for part in control_dirs.splitlines() if part.strip()]
    if control_dirs:
        resolved_dirs = [resolve_path(d, runtime.lora_next_root) for d in control_dirs]
        for d in resolved_dirs:
            if not Path(d).is_dir():
                raise AdapterError(f"参考图目录不存在: {d}")
        dataset["control_path"] = resolved_dirs

    train: dict[str, Any] = {
        "batch_size": int_value(source.get("train_batch_size") or source.get("batch_size"), 1) or 1,
        "steps": steps,
        "gradient_accumulation_steps": int_value(source.get("gradient_accumulation_steps"), 1) or 1,
        "gradient_checkpointing": truthy(source.get("gradient_checkpointing", True)),
        "noise_scheduler": "flowmatch",
        "timestep_type": "weighted",
        "optimizer": _map_optimizer(source.get("optimizer_type"), warnings),
        "lr": float_value(source.get("learning_rate"), 1e-4) or 1e-4,
        "dtype": "bf16",
    }
    if not is_empty(source.get("lr_scheduler")):
        train["lr_scheduler"] = str(source.get("lr_scheduler")).strip()
    if not is_empty(source.get("seed")):
        train["seed"] = int_value(source.get("seed"), 42)
    if truthy(source.get("use_ema")):
        train["ema_config"] = {
            "use_ema": True,
            "ema_decay": float_value(source.get("ema_decay"), 0.99) or 0.99,
        }

    model: dict[str, Any] = {
        "name_or_path": name_or_path,
        "arch": spec["arch"],
        "quantize": truthy(source.get("quantize", True)),
        "quantize_te": truthy(source.get("quantize_te", source.get("quantize", True))),
        "qtype": str(source.get("qtype") or "qfloat8"),
        "low_vram": truthy(source.get("low_vram", False)),
        "model_kwargs": {"match_target_res": False},
    }
    if truthy(source.get("layer_offloading")):
        model["layer_offloading"] = True

    save: dict[str, Any] = {
        "dtype": SAVE_DTYPE_MAP.get(str(source.get("save_precision") or "bf16").strip().lower(), "bf16"),
        "save_every": int_value(source.get("save_every_n_steps"), 250) or 250,
        "max_step_saves_to_keep": int_value(source.get("save_last_n_steps"), 4) or 4,
        "push_to_hub": False,
    }
    if not is_empty(source.get("save_every_n_epochs")):
        warnings.append("save_every_n_epochs 对 AI Toolkit 无效（无 epoch 概念），已忽略，以 save_every_n_steps 为准")

    process: dict[str, Any] = {
        "type": "sd_trainer",
        "training_folder": training_folder,
        "device": "cuda:0",
        "log_dir": log_dir,
        "logging": {"log_every": log_every},
        "network": {
            "type": "lora",
            "linear": int_value(source.get("network_dim"), 16) or 16,
            "linear_alpha": float_value(source.get("network_alpha"), 0) or int_value(source.get("network_dim"), 16) or 16,
        },
        "save": save,
        "datasets": [dataset],
        "train": train,
        "model": model,
    }
    if not is_empty(source.get("trigger_word")):
        process["trigger_word"] = str(source.get("trigger_word")).strip()

    prompts = _sample_prompt_lines(source.get("sample_prompts"))
    if prompts:
        res = _resolution_list(source.get("sample_resolution") or source.get("resolution"))
        width = height = res[0]
        if not is_empty(source.get("sample_width")):
            width = int_value(source.get("sample_width"), 1024)
        if not is_empty(source.get("sample_height")):
            height = int_value(source.get("sample_height"), 1024)
        process["sample"] = {
            "sampler": "flowmatch",
            "sample_every": int_value(source.get("sample_every_n_steps"), save["save_every"]) or save["save_every"],
            "width": width,
            "height": height,
            "prompts": prompts,
            "seed": int_value(source.get("sample_seed") or source.get("seed"), 42),
            "walk_seed": True,
            "guidance_scale": float_value(source.get("sample_cfg"), 4.0) or 4.0,
            "sample_steps": int_value(source.get("sample_steps"), 20) or 20,
            "neg": str(source.get("negative_prompts") or ""),
        }
        if not is_empty(source.get("sample_sampler")) and str(source.get("sample_sampler")).strip() != "flowmatch":
            warnings.append("Klein 训练采样仅支持 flowmatch，sample_sampler 已忽略")
    elif not is_empty(source.get("sample_sampler")) or not is_empty(source.get("sample_every_n_steps")):
        warnings.append("未提供 sample_prompts，采样设置已忽略")

    known = set(UI_ONLY_FIELDS) | {
        "pretrained_model_name_or_path", "dit", "text_encoder", "train_data_dir", "control_data_dirs",
        "caption_extension", "caption_dropout_rate", "shuffle_caption", "dataset_repeats",
        "resolution", "sample_resolution", "max_train_steps", "max_train_epochs",
        "train_batch_size", "batch_size", "gradient_accumulation_steps", "gradient_checkpointing",
        "optimizer_type", "learning_rate", "lr_scheduler", "seed", "use_ema", "ema_decay",
        "quantize", "quantize_te", "qtype", "low_vram", "layer_offloading",
        "output_dir", "output_name", "save_precision", "save_every_n_steps", "save_every_n_epochs",
        "save_last_n_steps", "network_dim", "network_alpha", "trigger_word",
        "sample_prompts", "sample_width", "sample_height", "sample_seed", "sample_cfg",
        "sample_steps", "sample_every_n_steps", "sample_sampler", "sample_at_first",
        "positive_prompts", "negative_prompts",
        "logging_dir", "gpu_ids",
    }
    for key in source:
        if key.startswith("_") or key in known:
            continue
        warnings.append(f"未知字段已忽略: {key}")

    config = {
        "job": "extension",
        "config": {
            "name": output_name,
            "process": [process],
        },
        "meta": {"name": output_name, "version": "1.0"},
    }
    return AdaptedConfig(config=config, warnings=warnings, te_path=te_path.resolve().as_posix())


def dump_yaml(config: dict[str, Any]) -> str:
    return yaml.safe_dump(config, sort_keys=False, allow_unicode=True, default_flow_style=False)

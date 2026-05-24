"""Validate training config imports against the current WebUI page train type."""

from __future__ import annotations

import copy
from typing import Any

ANIMA_TRAIN_TYPES = frozenset({"anima-lora", "sd3-lora"})
FLUX_TRAIN_TYPES = frozenset({"flux-lora", "flux-finetune"})
LUMINA_TRAIN_TYPES = frozenset({"lumina-lora"})
SDXL_TRAIN_TYPES = frozenset({"sdxl-lora", "sdxl-finetune"})
SD_TRAIN_TYPES = frozenset({"sd-lora", "sd-dreambooth"})
DREAMBOOTH_TRAIN_TYPES = frozenset({"sd-dreambooth", "sdxl-finetune"})

ANIMA_CONFIG_MARKERS = frozenset({
    "qwen3",
    "llm_adapter_path",
    "t5_tokenizer_path",
    "qwen3_max_token_length",
    "t5_max_token_length",
    "vae_chunk_size",
    "vae_disable_cache",
    "unsloth_offload_checkpointing",
})

FLUX_CONFIG_MARKERS = frozenset({
    "ae",
    "clip_l",
    "t5xxl",
    "t5xxl_max_token_length",
    "train_t5xxl",
    "apply_t5_attn_mask",
    "model_type",
    "guidance_scale",
    "model_prediction_type",
})

LUMINA_CONFIG_MARKERS = frozenset({
    "gemma2",
})

SDXL_CONFIG_MARKERS = frozenset({
    "sdxl_prediction_type",
    "learning_rate_te1",
    "learning_rate_te2",
})

TRAIN_TYPE_ALIASES = {
    "sd3-lora": "anima-lora",
}

PAGE_SPECS: dict[str, dict[str, Any]] = {
    "sd3-lora": {
        "label": "Anima LoRA 训练",
        "path": "/lora/sd3.html",
        "accepted": ANIMA_TRAIN_TYPES,
        "default_train_type": "anima-lora",
    },
    "flux-lora": {
        "label": "Flux LoRA 训练",
        "path": "/lora/flux.html",
        "accepted": FLUX_TRAIN_TYPES,
        "default_train_type": "flux-lora",
    },
    "lumina-lora": {
        "label": "Lumina LoRA 训练",
        "path": "/lora/lumina.html",
        "accepted": LUMINA_TRAIN_TYPES,
        "default_train_type": "lumina-lora",
    },
    "lora-master": {
        "label": "LoRA 训练（专家模式）",
        "path": "/lora/master.html",
        "accepted": SD_TRAIN_TYPES | SDXL_TRAIN_TYPES,
        "default_train_type": None,
    },
    "lora-basic": {
        "label": "LoRA 训练（新手模式）",
        "path": "/lora/basic.html",
        "accepted": SD_TRAIN_TYPES,
        "default_train_type": "sd-lora",
    },
    "sdxl-lora": {
        "label": "SDXL LoRA 训练",
        "path": "/lora/master.html",
        "accepted": SDXL_TRAIN_TYPES,
        "default_train_type": "sdxl-lora",
    },
    "dreambooth": {
        "label": "Dreambooth 训练",
        "path": "/dreambooth/",
        "accepted": DREAMBOOTH_TRAIN_TYPES,
        "default_train_type": None,
    },
}

TRAIN_TYPE_TARGETS: dict[str, dict[str, str]] = {
    "anima-lora": {"path": "/lora/sd3.html", "label": "Anima LoRA 训练"},
    "sd3-lora": {"path": "/lora/sd3.html", "label": "Anima LoRA 训练"},
    "flux-lora": {"path": "/lora/flux.html", "label": "Flux LoRA 训练"},
    "flux-finetune": {"path": "/lora/flux.html", "label": "Flux 训练"},
    "lumina-lora": {"path": "/lora/lumina.html", "label": "Lumina LoRA 训练"},
    "sdxl-lora": {"path": "/lora/master.html", "label": "SDXL LoRA 训练"},
    "sdxl-finetune": {"path": "/lora/master.html", "label": "SDXL 训练"},
    "sd-lora": {"path": "/lora/master.html", "label": "LoRA 训练（专家模式）"},
    "sd-dreambooth": {"path": "/dreambooth/", "label": "Dreambooth 训练"},
}


def _is_present(config: dict, key: str) -> bool:
    if key not in config:
        return False
    value = config[key]
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _has_markers(config: dict, markers: frozenset[str]) -> bool:
    return any(_is_present(config, key) for key in markers)


def _normalize_train_type(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    return TRAIN_TYPE_ALIASES.get(value, value)


def _family_of(train_type: str | None) -> str | None:
    if train_type is None:
        return None
    if train_type in ANIMA_TRAIN_TYPES:
        return "anima"
    if train_type in FLUX_TRAIN_TYPES:
        return "flux"
    if train_type in LUMINA_TRAIN_TYPES:
        return "lumina"
    if train_type in SDXL_TRAIN_TYPES:
        return "sdxl"
    if train_type in SD_TRAIN_TYPES:
        return "sd"
    if train_type in DREAMBOOTH_TRAIN_TYPES:
        return "dreambooth"
    return train_type


def infer_train_type(config: dict) -> str | None:
    """Infer training type from explicit field and model-specific markers."""
    network_module = str(config.get("network_module", ""))
    if network_module == "networks.lora_anima":
        return "anima-lora"

    explicit = _normalize_train_type(config.get("model_train_type"))
    has_anima = _has_markers(config, ANIMA_CONFIG_MARKERS)
    has_flux = _has_markers(config, FLUX_CONFIG_MARKERS)
    has_lumina = _has_markers(config, LUMINA_CONFIG_MARKERS)
    has_sdxl = _has_markers(config, SDXL_CONFIG_MARKERS)

    if has_anima:
        return "anima-lora"
    if has_flux and not has_lumina:
        return "flux-lora"
    if has_lumina:
        return "lumina-lora"

    if explicit:
        if explicit in SDXL_TRAIN_TYPES and has_sdxl:
            return explicit
        if explicit in ANIMA_TRAIN_TYPES:
            return "anima-lora"
        return explicit

    if has_sdxl:
        return "sdxl-lora"

    return None


def _resolve_page_spec(page_train_type: str) -> dict[str, Any] | None:
    normalized = TRAIN_TYPE_ALIASES.get(page_train_type, page_train_type)
    return PAGE_SPECS.get(normalized) or PAGE_SPECS.get(page_train_type)


def _normalize_for_page(config: dict, page_spec: dict[str, Any], config_type: str | None) -> dict:
    normalized = copy.deepcopy(config)
    default_type = page_spec.get("default_train_type")
    accepted = page_spec.get("accepted") or frozenset()

    if default_type:
        normalized["model_train_type"] = default_type
    elif config_type and config_type in accepted:
        normalized["model_train_type"] = config_type
    elif config_type:
        normalized["model_train_type"] = config_type

    return normalized


def validate_config_import(page_train_type: str, config: dict) -> dict[str, Any]:
    """
    Validate imported config against the current page.

    Returns a dict with ``result`` in {ok, redirect, reject}.
    """
    if not isinstance(config, dict):
        return {
            "result": "reject",
            "errors": ["配置必须是 JSON 对象 / TOML 表"],
        }

    page_spec = _resolve_page_spec(page_train_type)
    if page_spec is None:
        return {
            "result": "ok",
            "config": copy.deepcopy(config),
            "message": "当前页面未配置导入校验规则，已允许导入",
        }

    inferred = infer_train_type(config)
    explicit = _normalize_train_type(config.get("model_train_type"))
    config_type = inferred or explicit
    accepted = page_spec["accepted"]

    if config_type is None:
        normalized = _normalize_for_page(config, page_spec, None)
        return {
            "result": "ok",
            "config": normalized,
            "forced_train_type": normalized.get("model_train_type"),
            "message": "已按当前页面补全训练类型",
        }

    if config_type in accepted:
        normalized = _normalize_for_page(config, page_spec, config_type)
        return {
            "result": "ok",
            "config": normalized,
            "forced_train_type": normalized.get("model_train_type"),
            "message": "配置与当前训练页面匹配",
        }

    # Stale explicit type on the correct page family (e.g. sd3-lora on Anima page).
    if explicit and _normalize_train_type(explicit) in accepted and inferred in accepted:
        normalized = _normalize_for_page(config, page_spec, inferred)
        return {
            "result": "ok",
            "config": normalized,
            "forced_train_type": normalized.get("model_train_type"),
            "message": "已兼容旧版训练类型命名并规范化",
        }

    target = TRAIN_TYPE_TARGETS.get(config_type)
    if target is None:
        return {
            "result": "reject",
            "errors": [
                f"无法识别训练类型 model_train_type={config.get('model_train_type')!r}，"
                "请确认配置文件来源",
            ],
        }

    page_label = page_spec["label"]
    target_label = target["label"]
    return {
        "result": "redirect",
        "config": copy.deepcopy(config),
        "target_path": target["path"],
        "target_label": target_label,
        "config_train_type": config_type,
        "message": (
            f"检测到这是「{target_label}」配置（model_train_type={config.get('model_train_type')!r}），"
            f"与当前「{page_label}」页面不匹配。"
            f"是否跳转到 {target_label} 页面并导入？"
        ),
    }

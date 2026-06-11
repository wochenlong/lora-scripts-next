"""Validate training config imports against the current WebUI page train type."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

ANIMA_TRAIN_TYPES = frozenset({"anima-lora", "sd3-lora"})
FLUX_TRAIN_TYPES = frozenset({"flux-lora", "flux-finetune"})
LUMINA_TRAIN_TYPES = frozenset({"lumina-lora"})
SDXL_TRAIN_TYPES = frozenset({"sdxl-lora", "sdxl-finetune"})
SD_TRAIN_TYPES = frozenset({"sd-lora", "sd-dreambooth"})
DREAMBOOTH_TRAIN_TYPES = frozenset({"sd-dreambooth", "sdxl-finetune"})

ANIMA_NETWORK_MODULES = frozenset({"networks.lora_anima", "networks.tlora_anima"})

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

MODEL_PATH_KEYS = (
    "pretrained_model_name_or_path",
    "vae",
    "qwen3",
    "llm_adapter_path",
    "t5_tokenizer_path",
    "ae",
    "clip_l",
    "t5xxl",
    "gemma2",
    "network_weights",
    "resume",
)

ANIMA_PATH_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/anima/", re.I), "模型路径含 /anima/"),
    (re.compile(r"anima[-_]?base", re.I), "主模型路径含 anima-base"),
    (re.compile(r"qwen_image_vae", re.I), "VAE 路径含 qwen_image_vae"),
    (re.compile(r"qwen_3_06b", re.I), "文本模型路径含 qwen_3_06b"),
    (re.compile(r"qwen3", re.I), "文本模型路径含 qwen3"),
)

FLUX_PATH_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/flux/", re.I), "模型路径含 /flux/"),
    (re.compile(r"flux[-_]?dev", re.I), "主模型路径含 flux"),
    (re.compile(r"t5xxl", re.I), "路径含 t5xxl"),
    (re.compile(r"clip_l", re.I), "路径含 clip_l"),
    (re.compile(r"/ae/", re.I), "路径含 ae 模型"),
)

SDXL_PATH_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/sdxl/", re.I), "模型路径含 /sdxl/"),
    (re.compile(r"sdxl[-_]", re.I), "主模型路径含 sdxl"),
    (re.compile(r"noobxl|pony|illustrious", re.I), "主模型路径为常见 SDXL 模型"),
)

LUMINA_PATH_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/lumina/", re.I), "模型路径含 /lumina/"),
    (re.compile(r"gemma2", re.I), "路径含 gemma2"),
)

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


@dataclass
class TrainTypeAnalysis:
    train_type: str | None
    reasons: list[str] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)


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


def _normalize_path_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\\", "/").lower()


def _collect_path_reasons(
    config: dict,
    rules: tuple[tuple[re.Pattern[str], str], ...],
) -> list[str]:
    reasons: list[str] = []
    seen: set[str] = set()
    for key in MODEL_PATH_KEYS:
        path = _normalize_path_value(config.get(key))
        if not path:
            continue
        for pattern, label in rules:
            if not pattern.search(path):
                continue
            detail = f"{key} → {label}"
            if detail in seen:
                break
            seen.add(detail)
            reasons.append(detail)
            break
    return reasons


def _collect_prefix_key_reasons(config: dict, prefix: str, label: str) -> list[str]:
    return [
        f"字段 {key}"
        for key in sorted(config)
        if key.startswith(prefix) and _is_present(config, key)
    ]


def _score_family(
    config: dict,
    *,
    marker_keys: frozenset[str],
    path_rules: tuple[tuple[re.Pattern[str], str], ...],
    prefix: str | None = None,
    prefix_label: str | None = None,
    network_modules: frozenset[str] | None = None,
    marker_weight: int = 3,
    path_weight: int = 4,
    prefix_weight: int = 3,
    network_weight: int = 10,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if network_modules:
        network_module = str(config.get("network_module", ""))
        if network_module in network_modules:
            score += network_weight
            reasons.append(f"network_module={network_module}")

    for key in marker_keys:
        if _is_present(config, key):
            score += marker_weight
            reasons.append(f"字段 {key}")

    for reason in _collect_path_reasons(config, path_rules):
        score += path_weight
        reasons.append(reason)

    if prefix and prefix_label:
        for reason in _collect_prefix_key_reasons(config, prefix, prefix_label):
            score += prefix_weight
            reasons.append(reason)

    return score, reasons


def analyze_train_type(config: dict) -> TrainTypeAnalysis:
    """Score config content across training families and return the best match."""
    families: list[tuple[str, int, list[str]]] = []

    anima_score, anima_reasons = _score_family(
        config,
        marker_keys=ANIMA_CONFIG_MARKERS,
        path_rules=ANIMA_PATH_RULES,
        prefix="anima_",
        prefix_label="Anima",
        network_modules=ANIMA_NETWORK_MODULES,
    )
    families.append(("anima-lora", anima_score, anima_reasons))

    flux_score, flux_reasons = _score_family(
        config,
        marker_keys=FLUX_CONFIG_MARKERS,
        path_rules=FLUX_PATH_RULES,
    )
    families.append(("flux-lora", flux_score, flux_reasons))

    lumina_score, lumina_reasons = _score_family(
        config,
        marker_keys=LUMINA_CONFIG_MARKERS,
        path_rules=LUMINA_PATH_RULES,
    )
    families.append(("lumina-lora", lumina_score, lumina_reasons))

    sdxl_score, sdxl_reasons = _score_family(
        config,
        marker_keys=SDXL_CONFIG_MARKERS,
        path_rules=SDXL_PATH_RULES,
    )
    families.append(("sdxl-lora", sdxl_score, sdxl_reasons))

    families.sort(key=lambda item: item[1], reverse=True)
    scores = {name: score for name, score, _ in families}
    best_name, best_score, best_reasons = families[0]

    if best_score >= 2:
        return TrainTypeAnalysis(train_type=best_name, reasons=best_reasons, scores=scores)

    explicit = _normalize_train_type(config.get("model_train_type"))
    if explicit:
        return TrainTypeAnalysis(train_type=explicit, reasons=[], scores=scores)

    return TrainTypeAnalysis(train_type=None, reasons=[], scores=scores)


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
    return analyze_train_type(config).train_type


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


def _format_reasons(reasons: list[str], limit: int = 4) -> str:
    if not reasons:
        return ""
    shown = reasons[:limit]
    text = "、".join(shown)
    if len(reasons) > limit:
        text += f" 等 {len(reasons)} 项"
    return text


def _build_type_notice(
    *,
    explicit: str | None,
    explicit_raw: str | None,
    normalized_type: str | None,
    inferred: str | None,
    reasons: list[str],
) -> str | None:
    if not normalized_type:
        return None

    target_label = TRAIN_TYPE_TARGETS.get(normalized_type, {}).get("label", normalized_type)
    reason_text = _format_reasons(reasons)
    reason_part = f"（依据：{reason_text}）" if reason_text else ""

    should_notify = False
    if isinstance(explicit_raw, str) and explicit_raw != normalized_type:
        should_notify = True
    elif explicit is None and reason_text:
        should_notify = True
    elif inferred and explicit and explicit != inferred:
        should_notify = True

    if not should_notify:
        return None

    if isinstance(explicit_raw, str) and explicit_raw != normalized_type:
        return (
            f"检测到配置为 {target_label} 内容{reason_part}，"
            f"已自动将 model_train_type 从 {explicit_raw!r} 切换为 {normalized_type!r}"
        )

    return (
        f"检测到 {target_label} 训练内容{reason_part}，"
        f"已自动切换为 {normalized_type!r}"
    )


def _looks_like_sd_scripts_toml(config: dict) -> bool:
    """Detect adapter output TOML that strips GUI-only fields (#31)."""
    if config.get("model_train_type") or config.get("lora_type"):
        return False
    if not config.get("network_module"):
        return False
    gui_only_markers = (
        "enable_preview",
        "positive_prompts",
        "negative_prompts",
        "sample_at_first",
    )
    return not any(key in config for key in gui_only_markers)


def _build_redirect_message(
    *,
    page_label: str,
    target_label: str,
    explicit_raw: str | None,
    config_type: str,
    reasons: list[str],
) -> str:
    reason_text = _format_reasons(reasons)
    reason_part = f"（依据：{reason_text}）" if reason_text else ""
    explicit_part = explicit_raw if explicit_raw is not None else config_type
    return (
        f"检测到这是「{target_label}」配置{reason_part}，"
        f"model_train_type={explicit_part!r} 与当前「{page_label}」页面不匹配。"
        f"是否跳转到 {target_label} 页面并导入？"
    )


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

    if _looks_like_sd_scripts_toml(config):
        return {
            "result": "reject",
            "errors": [
                "此文件像是 sd-scripts 中间格式（*-sd-scripts.toml），缺少 GUI 字段 model_train_type / lora_type。",
                "请导入不带 -sd-scripts 后缀的 GUI 配置文件（config/autosave 下的 autosave TOML 或页面导出的配置）。",
            ],
        }

    page_spec = _resolve_page_spec(page_train_type)
    if page_spec is None:
        return {
            "result": "ok",
            "config": copy.deepcopy(config),
            "message": "当前页面未配置导入校验规则，已允许导入",
        }

    analysis = analyze_train_type(config)
    inferred = analysis.train_type
    explicit = _normalize_train_type(config.get("model_train_type"))
    explicit_raw = config.get("model_train_type")
    config_type = inferred or explicit
    accepted = page_spec["accepted"]
    detection_reasons = analysis.reasons

    if config_type is None:
        normalized = _normalize_for_page(config, page_spec, None)
        notice = _build_type_notice(
            explicit=explicit,
            explicit_raw=explicit_raw if isinstance(explicit_raw, str) else None,
            normalized_type=normalized.get("model_train_type"),
            inferred=inferred,
            reasons=detection_reasons,
        )
        return {
            "result": "ok",
            "config": normalized,
            "forced_train_type": normalized.get("model_train_type"),
            "inferred_train_type": inferred,
            "detection_reasons": detection_reasons,
            "notice": notice,
            "message": notice or "已按当前页面补全训练类型",
        }

    if config_type in accepted:
        normalized = _normalize_for_page(config, page_spec, config_type)
        normalized_type = normalized.get("model_train_type")
        notice = _build_type_notice(
            explicit=explicit,
            explicit_raw=explicit_raw if isinstance(explicit_raw, str) else None,
            normalized_type=normalized_type,
            inferred=inferred,
            reasons=detection_reasons,
        )
        return {
            "result": "ok",
            "config": normalized,
            "forced_train_type": normalized_type,
            "inferred_train_type": inferred,
            "detection_reasons": detection_reasons,
            "notice": notice,
            "message": notice or "配置与当前训练页面匹配",
        }

    # Stale explicit type on the correct page family (e.g. sd3-lora on Anima page).
    if explicit and _normalize_train_type(explicit) in accepted and inferred in accepted:
        normalized = _normalize_for_page(config, page_spec, inferred)
        normalized_type = normalized.get("model_train_type")
        notice = _build_type_notice(
            explicit=explicit,
            explicit_raw=explicit_raw if isinstance(explicit_raw, str) else None,
            normalized_type=normalized_type,
            inferred=inferred,
            reasons=detection_reasons,
        )
        return {
            "result": "ok",
            "config": normalized,
            "forced_train_type": normalized_type,
            "inferred_train_type": inferred,
            "detection_reasons": detection_reasons,
            "notice": notice,
            "message": notice or "已兼容旧版训练类型命名并规范化",
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
        "inferred_train_type": inferred,
        "detection_reasons": detection_reasons,
        "message": _build_redirect_message(
            page_label=page_label,
            target_label=target_label,
            explicit_raw=explicit_raw if isinstance(explicit_raw, str) else None,
            config_type=config_type,
            reasons=detection_reasons,
        ),
    }

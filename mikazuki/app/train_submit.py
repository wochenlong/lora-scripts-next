"""Shared /api/run submission helpers (engine-agnostic).

Extracted from ``mikazuki.app.api`` so engine packs (``mikazuki/engines/*/run.py``)
can reuse the sample-prompt / sanitize / defaults pipeline without importing the
API router module. Behavior is byte-identical to the previous in-place helpers.
"""

import math
import os
import random
import sys

from glob import glob
from typing import Optional, Tuple

try:
    import toml
except ModuleNotFoundError:  # pragma: no cover - lightweight test environment fallback
    import tomllib

    class _TomlFallback:
        @staticmethod
        def loads(content: str):
            return tomllib.loads(content)

        @staticmethod
        def dumps(data: dict):
            from mikazuki.engines.anima_fast.adapter import dump_flat_toml
            return dump_flat_toml(data)

    toml = _TomlFallback()

from mikazuki.app.models import APIResponseFail
from mikazuki.log import log
from mikazuki.portable_utils import flash_attn_stack_usable
from mikazuki.utils import train_utils
from mikazuki.utils.config_args import normalize_kv_arg_list

ANIMA_TRAIN_TYPES = {"anima-lora", "sd3-lora", "anima-finetune"}
ANIMA_FINETUNE_TYPE = "anima-finetune"
ANIMA_DEFAULT_SAMPLE_POSITIVE = (
    "1girl, solo, smile, japanese clothes, kimono, blue eyes, closed mouth, upper body, looki"
    "ng at viewer, hair ornament, long hair, yellow kimono, black hair, anime coloring, yukat"
    "a, choker, split mouth, side ponytail, bow, brown hair"
)
ANIMA_DEFAULT_SAMPLE_NEGATIVE = (
    "nsfw, explicit, sexual content, nude, naked, nipples, areola, genitals, cleavage, breast"
    "s, ass, buttocks, thighs, underwear, lingerie, bikini, swimsuit, erotic, suggestive, lew"
    "d, spread legs, close-up body, transparent clothes, worst quality, low quality, score_1,"
    " score_2, score_3, artist name, jpeg artifacts"
)
ANIMA_DEFAULT_UNET_LR = 5e-5
ANIMA_LEGACY_UNET_LR = {"0.0001", "1e-4", "1E-4"}
ANIMA_FULL_PRECISION_UNSAFE_OPTIMIZERS = {"automagic", "pytorch_optimizer.came"}


def _add_training_warning(config: dict, message: str) -> None:
    warnings = config.setdefault("_training_warnings", [])
    if isinstance(warnings, list) and message not in warnings:
        warnings.append(message)


def _missing_standard_train_field(field: str, label: str) -> APIResponseFail:
    return APIResponseFail(
        message=f"缺少 {label} ({field})，无法启动训练。请检查训练参数后重试。",
        data={"field": field},
    )


def _is_invalid_value(value) -> bool:
    """Check if a value is invalid and should be stripped before writing TOML."""
    if value is None:
        return True
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "undefined", "null", "nan"}:
        return True
    return False


_PATH_FIELDS = {
    "pretrained_model_name_or_path", "vae", "qwen3", "llm_adapter_path",
    "t5_tokenizer_path", "resume", "train_data_dir", "reg_data_dir",
    "output_dir", "logging_dir", "network_weights", "sample_prompts",
    "dit", "text_encoder", "turbo_dit",
}


def sanitize_config(config: dict) -> None:
    """Remove all invalid/empty values from config before writing TOML."""
    if sys.platform == "win32" and config.get("torch_compile"):
        log.warning(
            "torch_compile is not supported on Windows (requires Triton, Linux-only). "
            "Automatically disabled. / "
            "torch_compile 在 Windows 上不可用（需要仅限 Linux 的 Triton 库），已自动关闭。"
        )
        config.pop("torch_compile", None)
        config.pop("dynamo_backend", None)

    keys_to_remove = [k for k, v in config.items() if _is_invalid_value(v)]
    for k in keys_to_remove:
        del config[k]
    for key in ("network_args", "optimizer_args"):
        if isinstance(config.get(key), list):
            config[key] = normalize_kv_arg_list(config[key])
    for key in _PATH_FIELDS:
        if isinstance(config.get(key), str):
            config[key] = config[key].replace("\\", "/")


def get_sample_prompts(config: dict, model_train_type: str = "sd-lora") -> Tuple[Optional[str], str]:
    # backward compatibility
    if "sample_prompts" in config and "positive_prompts" not in config:
        return None, config["sample_prompts"]

    train_data_dir = config["train_data_dir"]
    sub_dir = [dir for dir in glob(os.path.join(train_data_dir, '*')) if os.path.isdir(dir)]

    use_anima_defaults = model_train_type in ANIMA_TRAIN_TYPES and is_preview_enabled(config)
    default_positive = ANIMA_DEFAULT_SAMPLE_POSITIVE if use_anima_defaults else None
    default_negative = ANIMA_DEFAULT_SAMPLE_NEGATIVE if use_anima_defaults else ''
    default_width = 1024 if use_anima_defaults else 512
    default_height = 1024 if use_anima_defaults else 512
    default_cfg = 4.5 if use_anima_defaults else 7
    default_seed = 42 if use_anima_defaults else 2333
    default_steps = 40 if use_anima_defaults else 24

    positive_prompts = train_utils.normalize_sample_prompt_text(config.pop('positive_prompts', default_positive))
    negative_prompts = train_utils.normalize_sample_prompt_text(config.pop('negative_prompts', default_negative))
    sample_width = config.pop('sample_width', default_width)
    sample_height = config.pop('sample_height', default_height)
    sample_cfg = config.pop('sample_cfg', default_cfg)
    sample_seed = config.pop('sample_seed', default_seed)
    sample_steps = config.pop('sample_steps', default_steps)
    sample_sampler = config.pop('sample_sampler', None)
    randomly_choice_prompt = config.pop('randomly_choice_prompt', False)

    if randomly_choice_prompt:
        if len(sub_dir) != 1:
            raise ValueError('训练数据集下有多个子文件夹，无法启用随机选取 Prompt 功能')

        txt_files = glob(os.path.join(sub_dir[0], '*.txt'))
        if not txt_files:
            raise ValueError('训练数据集路径没有 txt 文件')
        try:
            sample_prompt_file = random.choice(txt_files)
            with open(sample_prompt_file, 'r', encoding='utf-8') as f:
                positive_prompts = train_utils.normalize_sample_prompt_text(f.read())
        except IOError:
            log.error(f"读取 {sample_prompt_file} 文件失败")

    sample_prompts_arg = train_utils.build_sample_prompt_line(
        positive_prompts,
        negative_prompts,
        width=sample_width,
        height=sample_height,
        cfg=sample_cfg,
        steps=sample_steps,
        seed=sample_seed,
        sampler=sample_sampler if use_anima_defaults else None,
    )
    return positive_prompts, sample_prompts_arg


TOKENIZER_CACHE_TRAIN_TYPES = frozenset(
    {"sd-lora", "sdxl-lora", "sdxl-finetune", "flux-lora", "flux-finetune"}
)


def apply_tokenizer_cache_dir(config: dict, model_train_type: str) -> None:
    """Use bundled tokenizer-cache when available so SD/SDXL/Flux training works offline."""
    if model_train_type not in TOKENIZER_CACHE_TRAIN_TYPES:
        return
    if config.get("tokenizer_cache_dir"):
        return
    from mikazuki.tokenizer_cache import bundled_tokenizer_cache_dir

    cache_dir = bundled_tokenizer_cache_dir(train_type=model_train_type)
    if cache_dir:
        config["tokenizer_cache_dir"] = cache_dir


def apply_sdxl_prediction_type(config: dict, model_train_type: str):
    prediction_type = config.pop("sdxl_prediction_type", None)
    if model_train_type != "sdxl-lora":
        return
    if prediction_type is None:
        return

    if prediction_type == "v_prediction":
        config["v_parameterization"] = True
        config["flow_model"] = False
        config["contrastive_flow_matching"] = False
        return

    if prediction_type == "rectified_flow":
        config["flow_model"] = True
        config["v_parameterization"] = False
        config["scale_v_pred_loss_like_noise_pred"] = False
        return

    config["v_parameterization"] = False
    config["scale_v_pred_loss_like_noise_pred"] = False
    config["flow_model"] = False
    config["contrastive_flow_matching"] = False


def is_preview_enabled(config: dict) -> bool:
    return train_utils.is_preview_enabled(config)


def has_explicit_sample_prompt_source(config: dict) -> bool:
    return train_utils.has_explicit_sample_prompt_source(config)


def should_generate_sample_prompts(config: dict) -> bool:
    return train_utils.should_generate_sample_prompts(config)


def _detect_best_attn_mode() -> str:
    """Auto-detect the best available attention backend for Anima training."""
    if flash_attn_stack_usable():
        return "flash"
    try:
        import xformers  # noqa: F401
        return "xformers"
    except ImportError:
        pass
    return "torch"


def _cuda_bf16_supported() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available() and torch.cuda.is_bf16_supported())
    except Exception:
        return False


def _anima_lokr_training(config: dict) -> bool:
    lora_type = str(config.get("lora_type", "")).strip().lower()
    if lora_type == "lokr":
        return True

    network_module = str(config.get("network_module", "")).strip().lower()
    if network_module == "networks.lokr":
        return True

    lycoris_algo = str(config.get("lycoris_algo", "")).strip().lower()
    if lycoris_algo == "lokr":
        return True

    if network_module == "lycoris.kohya":
        for item in config.get("network_args") or []:
            if not isinstance(item, str):
                continue
            if item.strip().lower() == "algo=lokr":
                return True
    return False


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _anima_lokr_full_matrix_training(config: dict) -> bool:
    if not _anima_lokr_training(config):
        return False
    if _is_truthy(config.get("full_matrix")):
        return True
    for item in config.get("network_args") or []:
        if not isinstance(item, str) or "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key.strip().lower() == "full_matrix" and _is_truthy(value):
            return True
    return False


def _warn_lokr_precision_risks(config: dict) -> None:
    if not _anima_lokr_training(config):
        return

    mixed = str(config.get("mixed_precision", "")).strip().lower()
    full_key = "full_bf16" if mixed == "bf16" else "full_fp16" if mixed == "fp16" else None
    if full_key and not config.get(full_key):
        _add_training_warning(
            config,
            f"Anima LoKr mixed_precision={mixed} may require {full_key}=true to keep "
            "adapter and activation dtypes aligned. The trainer keeps your precision "
            "settings unchanged.",
        )
        log.warning(
            "Anima LoKr mixed_precision=%s may require %s=true to keep adapter and "
            "activation dtypes aligned. User precision settings are unchanged.",
            mixed,
            full_key,
        )

    if _anima_lokr_full_matrix_training(config):
        active_full_half = [
            key
            for key in ("full_bf16", "full_fp16")
            if config.get(key)
        ]
        if active_full_half or _is_invalid_value(config.get("scale_weight_norms")):
            _add_training_warning(
                config,
                "Anima LoKr full_matrix=true is a high-risk stability mode. "
                "Consider disabling full_bf16/full_fp16 and setting scale_weight_norms=1 "
                "if the first epoch becomes unstable. The trainer keeps your parameters unchanged.",
            )
            log.warning(
                "Anima LoKr full_matrix=true is a high-risk stability mode. "
                "User full precision and scale_weight_norms settings are unchanged."
            )


def apply_anima_training_defaults(config: dict, model_train_type: str):
    if model_train_type not in ANIMA_TRAIN_TYPES:
        return

    if model_train_type == ANIMA_FINETUNE_TYPE:
        lr = str(config.get("learning_rate", "")).strip()
        if not lr or lr in ANIMA_LEGACY_UNET_LR:
            unet_lr = str(config.get("unet_lr", "")).strip()
            if unet_lr and unet_lr not in ANIMA_LEGACY_UNET_LR:
                config["learning_rate"] = unet_lr
            else:
                config["learning_rate"] = "1e-5"
        config.pop("unet_lr", None)
        config.pop("text_encoder_lr", None)
    elif str(config.get("unet_lr", "")).strip() in ANIMA_LEGACY_UNET_LR:
        config["unet_lr"] = ANIMA_DEFAULT_UNET_LR
    elif isinstance(config.get("unet_lr"), str):
        config["unet_lr"] = float(config["unet_lr"])

    if is_preview_enabled(config) or config.get("sample_prompts"):
        config["sample_at_first"] = True

    optimizer_type = str(config.get("optimizer_type", "")).strip().lower()
    if optimizer_type in ANIMA_FULL_PRECISION_UNSAFE_OPTIMIZERS:
        if config.get("mixed_precision") == "fp16" and _cuda_bf16_supported():
            config["mixed_precision"] = "bf16"
            _add_training_warning(
                config,
                "Changed Anima mixed_precision from fp16 to bf16 for optimizer "
                f"{config.get('optimizer_type')}. fp16 is more likely to produce loss=nan.",
            )
            log.warning(
                "Changed Anima mixed_precision from fp16 to bf16 for optimizer "
                f"{config.get('optimizer_type')}. fp16 is more likely to produce loss=nan."
            )

        disabled = []
        for key in ("full_bf16", "full_fp16"):
            if config.pop(key, None):
                disabled.append(key)
        if disabled:
            _add_training_warning(
                config,
                "Disabled Anima full half-precision training for optimizer "
                f"{config.get('optimizer_type')} ({', '.join(disabled)}). "
                "This keeps trainable LoRA weights in fp32 to reduce loss=nan risk.",
            )
            log.warning(
                "Disabled Anima full half-precision training for optimizer "
                f"{config.get('optimizer_type')} ({', '.join(disabled)}). "
                "This keeps trainable LoRA weights in fp32 to reduce loss=nan risk."
            )
        _warn_lokr_precision_risks(config)
    elif _anima_lokr_full_matrix_training(config):
        _warn_lokr_precision_risks(config)
    elif _anima_lokr_training(config):
        _warn_lokr_precision_risks(config)

    requested_attn = config.get("attn_mode", "")
    if not requested_attn:
        best = _detect_best_attn_mode()
        config["attn_mode"] = best
        log.info(f"Anima attn_mode auto-detected: {best}")
    elif requested_attn == "xformers":
        try:
            import xformers  # noqa: F401
        except ImportError:
            best = _detect_best_attn_mode()
            config["attn_mode"] = best
            log.warning(
                f"attn_mode='xformers' requested but xformers is not installed, "
                f"falling back to '{best}'"
            )
    elif requested_attn == "flash":
        if not flash_attn_stack_usable():
            best = _detect_best_attn_mode()
            config["attn_mode"] = best
            log.warning(
                f"attn_mode='flash' requested but flash-attn is not available, "
                f"falling back to '{best}'"
            )

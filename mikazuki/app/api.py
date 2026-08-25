import asyncio
import hashlib
import json
import math
import os
import re
import random
import sys

from glob import glob
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional

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
            from mikazuki.anima_fast_backend.adapter import dump_flat_toml
            return dump_flat_toml(data)

    toml = _TomlFallback()
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from urllib.parse import quote

import mikazuki.process as process
from mikazuki import launch_utils
from mikazuki.anima_fast_backend import TRAIN_TYPE as ANIMA_FAST_TRAIN_TYPE
from mikazuki.anima_fast_backend.adapter import (
    AdapterError,
    adapt_config,
    dump_fast_dataset_toml,
    dump_flat_toml,
    ensure_fast_run_log_dirs,
)
from mikazuki.anima_fast_backend.extension_state import (
    STATE_INSTALLED_UNVERIFIED,
    STATE_READY,
    default_layout,
    read_extension_status,
    write_install_state,
)
from mikazuki.anima_fast_backend.environment import audit_environment, start_install_task
from mikazuki.anima_fast_backend.installer import build_install_plan, copy_source_snapshot, remove_extension
from mikazuki.anima_fast_backend.preflight import run_preflight
from mikazuki.anima_fast_backend.preview import apply_anima_fast_preview
from mikazuki.anima_fast_backend.preprocess import prepare_anima_fast_dataset, user_left_resized_empty
from mikazuki.anima_fast_backend.settings import discover_runtime, feature_enabled
from mikazuki.anima_fast_backend.source_root import InstallSourceError, resolve_install_source_root
from mikazuki.musubi_backend import TRAIN_TYPE as MUSUBI_TRAIN_TYPE
from mikazuki.model_assets import (
    check_assets as check_model_assets,
    resolve_train_type as resolve_model_asset_train_type,
    start_download_task as start_model_assets_download_task,
)
from mikazuki.musubi_backend.adapter import (
    AdapterError as MusubiAdapterError,
    adapt_config as adapt_musubi_config,
    dump_dataset_toml as dump_musubi_dataset_toml,
    dump_train_toml as dump_musubi_train_toml,
)
from mikazuki.musubi_backend.environment import (
    audit_environment as audit_musubi_environment,
    start_install_task as start_musubi_install_task,
)
from mikazuki.musubi_backend.extension_state import (
    STATE_READY as MUSUBI_STATE_READY,
    default_layout as musubi_default_layout,
    read_extension_status as read_musubi_extension_status,
    write_install_state as write_musubi_install_state,
)
from mikazuki.musubi_backend.installer import (
    build_install_plan as build_musubi_install_plan,
    remove_extension as remove_musubi_extension,
)
from mikazuki.musubi_backend.preflight import run_preflight as run_musubi_preflight
from mikazuki.musubi_backend.settings import (
    default_upstream_cache as musubi_default_upstream_cache,
    discover_runtime as discover_musubi_runtime,
    feature_enabled as musubi_feature_enabled,
    resolve_install_source_root as resolve_musubi_install_source_root,
)
from mikazuki.app.config import app_config
from mikazuki.app.models import (APIResponse, APIResponseFail,
                                 APIResponseSuccess, TaggerInterrogateRequest,
                                 TaggerPrefetchRequest)
from mikazuki.dataset_editor import router as dataset_editor_router
from mikazuki.log import log
from mikazuki.tagger.interrogator import available_interrogators
from mikazuki.tagger.jobs import run_interrogate_job, run_prefetch_job
from mikazuki.tagger.progress import tagger_progress
from mikazuki.tasks import tm
from mikazuki.train_log_hub import hub as train_log_hub
from mikazuki.utils import task_insights, train_utils
from mikazuki.utils.config_import import validate_config_import
from mikazuki.utils.config_export import normalize_config_for_export
from mikazuki.utils.config_args import normalize_custom_args, normalize_kv_arg_list
from mikazuki.utils.devices import printable_devices
from mikazuki.portable_utils import flash_attn_stack_usable
from mikazuki.utils import path_browser as path_browser_utils
from mikazuki.utils.tk_window import (open_directory_selector,
                                      open_file_selector,
                                      tkinter_available)

router = APIRouter()
router.include_router(dataset_editor_router)

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

avaliable_scripts = [
    "networks/extract_lora_from_models.py",
    "networks/extract_lora_from_dylora.py",
    "networks/merge_lora.py",
    "tools/merge_models.py",
]

avaliable_schemas = []
avaliable_presets = []

trainer_mapping = {
    "sd-lora": "./scripts/stable/train_network.py",
    "sdxl-lora": "./vendor/sd-scripts/sdxl_train_network.py",

    "sd-dreambooth": "./scripts/stable/train_db.py",
    "sdxl-finetune": "./scripts/stable/sdxl_train.py",

    "sd3-lora": "./scripts/dev/anima_train_network.py",
    "anima-lora": "./scripts/dev/anima_train_network.py",
    "anima-finetune": "./scripts/dev/anima_train.py",
    "flux-lora": "./scripts/dev/flux_train_network.py",
    "flux-finetune": "./scripts/dev/flux_train.py",
}


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


async def load_schemas():
    avaliable_schemas.clear()

    schema_dir = os.path.join(os.getcwd(), "mikazuki", "schema")
    schemas = sorted(os.listdir(schema_dir), key=lambda name: (os.path.splitext(name)[0] != "shared", name))

    def lambda_hash(x):
        return hashlib.md5(x.encode()).hexdigest()

    for schema_name in schemas:
        schema_id = os.path.splitext(schema_name)[0]
        with open(os.path.join(schema_dir, schema_name), encoding="utf-8") as f:
            content = f.read()
            avaliable_schemas.append({
                "name": schema_id,
                "schema": content,
                "hash": lambda_hash(content)
            })


async def load_presets():
    avaliable_presets.clear()

    preset_dir = os.path.join(os.getcwd(), "config", "presets")
    presets = os.listdir(preset_dir)

    for preset_name in presets:
        with open(os.path.join(preset_dir, preset_name), encoding="utf-8") as f:
            content = f.read()
            avaliable_presets.append(toml.loads(content))


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


def _anima_fast_runtime():
    return discover_runtime(lora_next_root=Path.cwd())


def _anima_fast_disabled_response():
    return APIResponseFail(
        message="Anima Fast plugin is temporarily disabled by maintainer (LORA_ENABLE_ANIMA_FAST=0)."
    )


def _write_anima_fast_toml(config: dict, timestamp: str, autosave_dir: str) -> tuple[Path, dict, list[str]]:
    runtime = _anima_fast_runtime()
    run_id = f"{timestamp}-anima-fast"
    preview_warnings = apply_anima_fast_preview(config, autosave_dir, run_id)
    adapted = adapt_config(config, runtime, run_id)
    warnings = list(adapted.warnings) + preview_warnings
    if user_left_resized_empty(config):
        warnings.append(
            "resized_image_dir 未填写；开始训练时将自动 resize 到 "
            ".cache/anima_fast/<train_data_dir 相对路径>/resized（同一数据集可复用）"
        )
    return _write_adapted_anima_fast_toml(adapted.values, warnings, run_id, autosave_dir)


def _write_adapted_anima_fast_toml(values: dict, warnings: list[str], run_id: str, autosave_dir: str) -> tuple[Path, dict, list[str]]:
    toml_file = Path(autosave_dir) / f"{run_id}.toml"
    dataset_file = Path(autosave_dir) / f"{run_id}-dataset.toml"
    ensure_fast_run_log_dirs(values)
    values["dataset_config"] = dataset_file.resolve().as_posix()
    dataset_file.write_text(dump_fast_dataset_toml(values), encoding="utf-8")
    toml_file.write_text(dump_flat_toml(values), encoding="utf-8")
    return toml_file, values, warnings


def _anima_fast_fail_from_preflight(result):
    errors = list(getattr(result, "errors", None) or [])
    if errors:
        detail = "; ".join(errors[:4])
        if len(errors) > 4:
            detail += f" …（共 {len(errors)} 项）"
        message = f"Anima Fast 预检查失败：{detail}"
    else:
        message = "Anima Fast 预检查失败（未返回具体原因，请修复插件或查看浏览器 Network 响应）"
    return APIResponseFail(message=message, data=result.as_dict())


def _anima_fast_ready_gate():
    layout = default_layout(Path.cwd())
    status = read_extension_status(layout)
    if status.state != STATE_READY:
        return False, APIResponseFail(
            message="Anima Fast extension is not ready. Install or repair the extension first.",
            data=status.as_dict(),
        )
    audit = (status.facts or {}).get("audit", {})
    if not audit.get("ok"):
        return False, APIResponseFail(
            message="Anima Fast environment audit has not passed. Repair the extension before training.",
            data=status.as_dict(),
        )
    audit_result = audit_environment(Path.cwd(), layout, main_python=Path(sys.executable), require_cuda=True)
    if not audit_result.ok:
        write_install_state(layout, "broken", {"audit": audit_result.as_dict()}, "; ".join(audit_result.errors))
        return False, APIResponseFail(
            message="Anima Fast environment drift detected. Repair the extension before training.",
            data=audit_result.as_dict(),
        )
    return True, None


def _musubi_runtime():
    return discover_musubi_runtime(lora_next_root=Path.cwd())


def _musubi_disabled_response():
    return APIResponseFail(
        message="musubi-tuner backend is temporarily disabled by maintainer (LORA_ENABLE_MUSUBI=0)."
    )


def _musubi_ready_gate():
    layout = musubi_default_layout(Path.cwd())
    status = read_musubi_extension_status(layout)
    if status.state != MUSUBI_STATE_READY:
        return False, APIResponseFail(
            message="musubi-tuner 插件未就绪。请先在「设置 → 训练引擎」安装或修复 musubi-tuner 插件。",
            data=status.as_dict(),
        )
    audit = (status.facts or {}).get("audit", {})
    if not audit.get("ok"):
        return False, APIResponseFail(
            message="musubi-tuner 环境审计未通过。请先修复插件再训练。",
            data=status.as_dict(),
        )
    drift = audit_musubi_environment(_musubi_runtime())
    if not drift.ok:
        write_musubi_install_state(layout, "broken", {"audit": drift.as_dict()}, "; ".join(drift.errors))
        return False, APIResponseFail(
            message="musubi-tuner 环境发生漂移。请先修复插件再训练。",
            data=drift.as_dict(),
        )
    return True, None


def _musubi_fail_from_preflight(result):
    errors = list(getattr(result, "errors", None) or [])
    if errors:
        detail = "; ".join(errors[:4])
        if len(errors) > 4:
            detail += f" …（共 {len(errors)} 项）"
        message = f"musubi-tuner 预检查失败：{detail}"
    else:
        message = "musubi-tuner 预检查失败（未返回具体原因）"
    return APIResponseFail(message=message, data=result.as_dict())


def _musubi_apply_sample_defaults(config: dict) -> None:
    """Krea 2 sampling defaults: 1024px; Turbo schedule wants CFG off + few steps."""
    config.setdefault("sample_width", 1024)
    config.setdefault("sample_height", 1024)
    turbo = str(config.get("turbo_dit", "") or "").strip()
    if turbo:
        config.setdefault("sample_cfg", 1)
        config.setdefault("sample_steps", 8)
    else:
        config.setdefault("sample_cfg", 4.5)
        config.setdefault("sample_steps", 28)


@router.post("/config/validate-import")
async def validate_import_config(request: Request):
    """Validate imported TOML/JSON config against the current training page."""
    try:
        payload = json.loads(await request.body())
    except json.JSONDecodeError:
        return APIResponseFail(message="请求体必须是 JSON")

    page_train_type = payload.get("page_train_type")
    config = payload.get("config")
    if not page_train_type or not isinstance(page_train_type, str):
        return APIResponseFail(message="缺少 page_train_type")
    if not isinstance(config, dict):
        return APIResponseFail(message="缺少 config 对象")

    result = validate_config_import(page_train_type, config)
    return APIResponseSuccess(data=result)


@router.post("/config/normalize-for-export")
async def normalize_export_config(request: Request):
    """Normalize form config for export/download TOML (Anima uses adapt_anima_config)."""
    try:
        payload = json.loads(await request.body())
    except json.JSONDecodeError:
        return APIResponseFail(message="请求体必须是 JSON")

    page_train_type = payload.get("page_train_type")
    config = payload.get("config")
    if not page_train_type or not isinstance(page_train_type, str):
        return APIResponseFail(message="缺少 page_train_type")
    if not isinstance(config, dict):
        return APIResponseFail(message="缺少 config 对象")

    try:
        cfg, warnings = normalize_config_for_export(
            config,
            page_train_type=page_train_type,
        )
    except Exception as exc:
        log.exception("normalize-for-export failed")
        return APIResponseFail(message=f"预览配置失败: {exc}")

    return APIResponseSuccess(data={"config": cfg, "warnings": warnings})


@router.post("/run")
async def create_toml_file(request: Request):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    autosave_dir = os.path.join(os.getcwd(), "config", "autosave")
    os.makedirs(autosave_dir, exist_ok=True)
    toml_file = os.path.join(autosave_dir, f"{timestamp}.toml")
    json_data = await request.body()

    config: dict = json.loads(json_data.decode("utf-8"))
    train_utils.fix_config_types(config)
    normalize_custom_args(config)
    train_utils.ensure_enable_preview_flag(config)

    gpu_ids = config.pop("gpu_ids", None)

    model_train_type = config.pop("model_train_type", "sd-lora")
    if model_train_type == ANIMA_FAST_TRAIN_TYPE:
        if not feature_enabled():
            return _anima_fast_disabled_response()
        ready, failure = _anima_fast_ready_gate()
        if not ready:
            return failure
        try:
            runtime = _anima_fast_runtime()
            run_id = f"{timestamp}-anima-fast"
            preview_warnings = apply_anima_fast_preview(config, autosave_dir, run_id)
            prepared = prepare_anima_fast_dataset(config, runtime, run_id)
            adapted = prepared.adapted
            preflight = run_preflight(adapted.values, runtime)
            if not preflight.ok:
                return _anima_fast_fail_from_preflight(preflight)
            toml_file, adapted_values, warnings = _write_adapted_anima_fast_toml(
                adapted.values, [*adapted.warnings, *preview_warnings, *preflight.warnings], run_id, autosave_dir
            )
            metadata = {
                "progress_jsonl": adapted_values.get("progress_jsonl"),
                "output_dir": adapted_values.get("output_dir"),
                "output_name": adapted_values.get("output_name"),
                "logging_dir": adapted_values.get("logging_dir"),
                "warnings": warnings,
                "auto_resized": prepared.auto_resized,
            }
            return process.run_anima_fast_train(str(toml_file), runtime, gpu_ids, metadata=metadata)
        except AdapterError as exc:
            return APIResponseFail(message=str(exc))
        except Exception as exc:  # noqa: BLE001 - keep API failures structured
            log.error(f"Anima Fast launch failed: {exc}")
            return APIResponseFail(message=f"Anima Fast launch failed: {exc}")

    if model_train_type == MUSUBI_TRAIN_TYPE:
        if not musubi_feature_enabled():
            return _musubi_disabled_response()
        ready, failure = _musubi_ready_gate()
        if not ready:
            return failure
        try:
            runtime = _musubi_runtime()
            train_data_dir = str(config.get("train_data_dir") or "").strip()
            if not train_data_dir:
                return _missing_standard_train_field("train_data_dir", "训练数据集路径")
            if not train_utils.validate_data_dir(train_data_dir):
                return APIResponseFail(message="训练数据集路径不存在或没有图片，请检查目录。")

            if "prompt_file" in config and str(config["prompt_file"]).strip() != "":
                prompt_file = str(config["prompt_file"]).strip()
                if not os.path.exists(prompt_file):
                    return APIResponseFail(message=f"Prompt 文件 {prompt_file} 不存在，请检查路径。")
                config["sample_prompts"] = prompt_file
                train_utils.normalize_sample_prompt_file(prompt_file)
            elif should_generate_sample_prompts(config):
                _musubi_apply_sample_defaults(config)
                try:
                    positive_prompt, sample_prompts_arg = get_sample_prompts(config=config, model_train_type=model_train_type)
                    if positive_prompt is not None and train_utils.is_promopt_like(sample_prompts_arg):
                        sample_prompts_file = os.path.join(autosave_dir, f"{timestamp}-promopt.txt")
                        with open(sample_prompts_file, "w", encoding="utf-8", newline="\n") as f:
                            f.write(sample_prompts_arg + "\n")
                        config["sample_prompts"] = sample_prompts_file
                        log.info(f"Wrote prompts to file {sample_prompts_file}")
                except ValueError as e:
                    log.error(f"Error while processing prompts: {e}")
                    return APIResponseFail(message=str(e))
            else:
                train_utils.strip_disabled_preview_fields(config)

            if config.get("sample_prompts"):
                train_utils.normalize_sample_prompt_file(str(config["sample_prompts"]))
            else:
                config.pop("sample_at_first", None)
                config.pop("sample_every_n_epochs", None)
                config.pop("sample_every_n_steps", None)

            sanitize_config(config)

            run_id = f"{timestamp}-musubi"
            adapted = adapt_musubi_config(config, runtime, run_id)
            preflight = run_musubi_preflight(adapted.values, runtime, adapted.dataset)
            if not preflight.ok:
                return _musubi_fail_from_preflight(preflight)
            toml_file_path = Path(autosave_dir) / f"{run_id}.toml"
            dataset_file_path = Path(autosave_dir) / f"{run_id}-dataset.toml"
            dataset_file_path.write_text(dump_musubi_dataset_toml(adapted.dataset), encoding="utf-8")
            adapted.values["dataset_config"] = dataset_file_path.resolve().as_posix()
            toml_file_path.write_text(dump_musubi_train_toml(adapted.values), encoding="utf-8")

            metadata = {
                "output_dir": adapted.values.get("output_dir"),
                "output_name": adapted.values.get("output_name"),
                "logging_dir": adapted.values.get("logging_dir"),
                "warnings": [*adapted.warnings, *preflight.warnings],
            }
            return process.run_musubi_train(
                str(toml_file_path), runtime, adapted.values, gpu_ids, metadata=metadata
            )
        except MusubiAdapterError as exc:
            return APIResponseFail(message=str(exc))
        except Exception as exc:  # noqa: BLE001 - keep API failures structured
            log.error(f"musubi-tuner launch failed: {exc}")
            return APIResponseFail(message=f"musubi-tuner launch failed: {exc}")

    if model_train_type not in trainer_mapping:
        return APIResponseFail(
            message=f"不支持的训练类型: {model_train_type}",
            data={"model_train_type": model_train_type},
        )

    train_data_dir = str(config.get("train_data_dir") or "").strip()
    if not train_data_dir:
        return _missing_standard_train_field("train_data_dir", "训练数据集路径")
    config["train_data_dir"] = train_data_dir

    pretrained_model = str(config.get("pretrained_model_name_or_path") or "").strip()
    if not pretrained_model:
        return _missing_standard_train_field("pretrained_model_name_or_path", "底模路径")
    config["pretrained_model_name_or_path"] = pretrained_model

    suggest_cpu_threads = 8 if len(train_utils.get_total_images(train_data_dir, limit=200)) >= 200 else 2
    trainer_file = trainer_mapping[model_train_type]
    apply_sdxl_prediction_type(config, model_train_type)
    apply_anima_training_defaults(config, model_train_type)

    if model_train_type != "sdxl-finetune":
        if not train_utils.validate_data_dir(train_data_dir):
            return APIResponseFail(message="训练数据集路径不存在或没有图片，请检查目录。")

    validated, message = train_utils.validate_model(pretrained_model, model_train_type)
    if not validated:
        return APIResponseFail(message=message)

    if "prompt_file" in config and config["prompt_file"].strip() != "":
        prompt_file = config["prompt_file"].strip()
        if not os.path.exists(prompt_file):
            return APIResponseFail(message=f"Prompt 文件 {prompt_file} 不存在，请检查路径。")
        config["sample_prompts"] = prompt_file
        train_utils.normalize_sample_prompt_file(prompt_file)
    elif should_generate_sample_prompts(config):
        try:
            positive_prompt, sample_prompts_arg = get_sample_prompts(config=config, model_train_type=model_train_type)

            if positive_prompt is not None and train_utils.is_promopt_like(sample_prompts_arg):
                sample_prompts_file = os.path.join(autosave_dir, f"{timestamp}-promopt.txt")
                with open(sample_prompts_file, "w", encoding="utf-8", newline="\n") as f:
                    f.write(sample_prompts_arg + "\n")
                config["sample_prompts"] = sample_prompts_file
                log.info(f"Wrote prompts to file {sample_prompts_file}")

        except ValueError as e:
            log.error(f"Error while processing prompts: {e}")
            return APIResponseFail(message=str(e))
    else:
        train_utils.strip_disabled_preview_fields(config)

    if config.get("sample_prompts"):
        train_utils.normalize_sample_prompt_file(str(config["sample_prompts"]))

    apply_anima_training_defaults(config, model_train_type)
    apply_tokenizer_cache_dir(config, model_train_type)
    sanitize_config(config)

    if not config.get("sample_prompts"):
        config.pop("sample_at_first", None)
        config.pop("sample_every_n_epochs", None)
        config.pop("sample_every_n_steps", None)

    with open(toml_file, "w", encoding="utf-8") as f:
        f.write(toml.dumps(config))

    result = process.run_train(toml_file, trainer_file, gpu_ids, suggest_cpu_threads)

    return result


@router.get("/plugins/anima-lora/status")
async def anima_lora_plugin_status():
    layout = default_layout(Path.cwd())
    status = read_extension_status(layout).as_dict()
    runtime = _anima_fast_runtime()
    runtime_available = runtime.python.is_file() and (runtime.anima_root / "train.py").is_file()
    status["feature_enabled"] = feature_enabled()
    status["runtime"] = {
        "anima_root": str(runtime.anima_root),
        "source_commit": runtime.source_commit,
        "python": str(runtime.python),
        "output_dir": str(runtime.output_dir),
        "logging_dir": str(runtime.logging_dir),
        "cache_dir": str(runtime.cache_dir),
        "external_runtime_exists": runtime_available,
    }
    return APIResponseSuccess(data=status)


@router.post("/plugins/anima-lora/preflight")
async def anima_lora_plugin_preflight(request: Request):
    config: dict = json.loads((await request.body()).decode("utf-8") or "{}")
    runtime = _anima_fast_runtime()
    autosave_dir = os.path.join(os.getcwd(), "config", "autosave")
    os.makedirs(autosave_dir, exist_ok=True)
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-anima-fast"
    try:
        preview_warnings = apply_anima_fast_preview(config, autosave_dir, run_id)
        adapted = adapt_config(config, runtime, run_id)
    except AdapterError as exc:
        return APIResponseFail(message=str(exc))
    result = run_preflight(adapted.values, runtime)
    result.warnings = [*adapted.warnings, *preview_warnings, *result.warnings]
    if result.ok:
        return APIResponseSuccess(data=result.as_dict())
    return _anima_fast_fail_from_preflight(result)


@router.post("/plugins/anima-lora/dry-run")
async def anima_lora_plugin_dry_run(request: Request):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    autosave_dir = os.path.join(os.getcwd(), "config", "autosave")
    os.makedirs(autosave_dir, exist_ok=True)
    config: dict = json.loads((await request.body()).decode("utf-8") or "{}")
    config.pop("gpu_ids", None)
    config.pop("model_train_type", None)
    try:
        toml_file, adapted_values, warnings = _write_anima_fast_toml(config, timestamp, autosave_dir)
    except AdapterError as exc:
        return APIResponseFail(message=str(exc))
    return APIResponseSuccess(data={
        "toml_path": str(toml_file),
        "config": adapted_values,
        "warnings": warnings,
    })


@router.get("/plugins/musubi/status")
async def musubi_plugin_status():
    layout = musubi_default_layout(Path.cwd())
    status = read_musubi_extension_status(layout).as_dict()
    runtime = _musubi_runtime()
    status["feature_enabled"] = musubi_feature_enabled()
    status["train_type"] = MUSUBI_TRAIN_TYPE
    status["runtime"] = {
        "musubi_root": str(runtime.musubi_root),
        "python": str(runtime.python),
        "output_dir": str(runtime.output_dir),
        "logging_dir": str(runtime.logging_dir),
        "cache_dir": str(runtime.cache_dir),
        "external_runtime_exists": runtime.python.is_file()
        and (runtime.musubi_root / "src" / "musubi_tuner").is_dir(),
    }
    return APIResponseSuccess(data=status)


@router.post("/plugins/musubi/preflight")
async def musubi_plugin_preflight(request: Request):
    if not musubi_feature_enabled():
        return _musubi_disabled_response()
    config: dict = json.loads((await request.body()).decode("utf-8") or "{}")
    runtime = _musubi_runtime()
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-musubi"
    try:
        adapted = adapt_musubi_config(config, runtime, run_id)
    except MusubiAdapterError as exc:
        return APIResponseFail(message=str(exc))
    result = run_musubi_preflight(adapted.values, runtime, adapted.dataset)
    result.warnings = [*adapted.warnings, *result.warnings]
    if result.ok:
        return APIResponseSuccess(data=result.as_dict())
    return _musubi_fail_from_preflight(result)


@router.post("/plugins/musubi/dry-run")
async def musubi_plugin_dry_run(request: Request):
    if not musubi_feature_enabled():
        return _musubi_disabled_response()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    autosave_dir = os.path.join(os.getcwd(), "config", "autosave")
    os.makedirs(autosave_dir, exist_ok=True)
    config: dict = json.loads((await request.body()).decode("utf-8") or "{}")
    config.pop("gpu_ids", None)
    config.pop("model_train_type", None)
    runtime = _musubi_runtime()
    run_id = f"{timestamp}-musubi"
    try:
        adapted = adapt_musubi_config(config, runtime, run_id)
    except MusubiAdapterError as exc:
        return APIResponseFail(message=str(exc))
    toml_file_path = Path(autosave_dir) / f"{run_id}.toml"
    dataset_file_path = Path(autosave_dir) / f"{run_id}-dataset.toml"
    dataset_file_path.write_text(dump_musubi_dataset_toml(adapted.dataset), encoding="utf-8")
    adapted.values["dataset_config"] = dataset_file_path.resolve().as_posix()
    toml_file_path.write_text(dump_musubi_train_toml(adapted.values), encoding="utf-8")
    return APIResponseSuccess(data={
        "toml_path": str(toml_file_path),
        "dataset_toml_path": str(dataset_file_path),
        "config": adapted.values,
        "dataset": adapted.dataset,
        "warnings": adapted.warnings,
    })


@router.post("/plugins/musubi/install")
async def musubi_plugin_install(request: Request):
    return await _musubi_plugin_install_impl(request, force_install=False)


async def _musubi_plugin_install_impl(request: Request, force_install: bool = False):
    if not musubi_feature_enabled():
        return _musubi_disabled_response()
    payload: dict = json.loads((await request.body()).decode("utf-8") or "{}")
    source_commit = str(payload.get("source_commit") or "").strip() or None
    cuda_extra = str(payload.get("cuda_extra") or "").strip() or None
    dry_run = payload.get("dry_run", True) is not False
    project_root = Path.cwd()
    layout = musubi_default_layout(project_root)
    current_status = read_musubi_extension_status(layout)
    if not dry_run and not force_install and current_status.state == MUSUBI_STATE_READY:
        return APIResponseSuccess(data={
            "already_ready": True,
            "status": current_status.as_dict(),
            "message": "musubi-tuner plugin is already ready",
        })
    explicit = payload.get("source_root")
    try:
        source_root = resolve_musubi_install_source_root(
            project_root, Path(str(explicit)) if explicit else None, source_commit
        )
    except ValueError as exc:
        if dry_run:
            return APIResponseFail(message=str(exc))
        # Real install: let the background task auto-clone upstream into the cache
        # (mirrors the Anima Fast installer) so clone output streams to the install log.
        source_root = musubi_default_upstream_cache(project_root)
    plan = build_musubi_install_plan(source_root, layout, dry_run=dry_run, source_commit=source_commit)
    data = {"plan": plan.as_dict()}
    if dry_run:
        data["message"] = "Installer dry-run completed"
        return APIResponseSuccess(data=data)
    try:
        from mikazuki.download_sources import parse_download_sources

        task_id, install_data = start_musubi_install_task(
            project_root,
            layout,
            source_root,
            dry_run=False,
            source_commit=source_commit,
            cuda_extra=cuda_extra,
            download_sources=parse_download_sources(payload),
        )
    except Exception as exc:
        write_musubi_install_state(layout, "broken", {"plan": plan.as_dict()}, str(exc))
        return APIResponseFail(message=f"musubi-tuner install failed: {exc}")
    data.update(install_data)
    data["status"] = read_musubi_extension_status(layout).as_dict()
    data["message"] = "musubi-tuner install task started"
    return APIResponseSuccess(data=data)


@router.post("/plugins/musubi/repair")
async def musubi_plugin_repair(request: Request):
    return await _musubi_plugin_install_impl(request, force_install=True)


@router.post("/plugins/musubi/uninstall")
async def musubi_plugin_uninstall():
    if not musubi_feature_enabled():
        return _musubi_disabled_response()
    layout = musubi_default_layout(Path.cwd())
    try:
        remove_musubi_extension(layout, Path.cwd())
    except Exception as exc:
        return APIResponseFail(message=f"musubi-tuner uninstall failed: {exc}")
    return APIResponseSuccess(data={"status": read_musubi_extension_status(layout).as_dict()})


@router.post("/assets/check")
async def model_assets_check(request: Request):
    payload: dict = json.loads((await request.body()).decode("utf-8") or "{}")
    values = payload.get("values") or {}
    if not isinstance(values, dict):
        return APIResponseFail(message="values must be an object")
    train_type = resolve_model_asset_train_type(str(payload.get("train_type") or ""), values)
    return APIResponseSuccess(data={
        "train_type": train_type,
        "items": check_model_assets(train_type, values, Path.cwd()),
    })


@router.post("/assets/download")
async def model_assets_download(request: Request):
    payload: dict = json.loads((await request.body()).decode("utf-8") or "{}")
    values = payload.get("values") or {}
    items = payload.get("items") or []
    source = str(payload.get("source") or "")
    train_type = resolve_model_asset_train_type(str(payload.get("train_type") or ""), values if isinstance(values, dict) else {})
    if not items or not isinstance(items, list):
        return APIResponseFail(message="items must be a non-empty list")
    if source not in {"huggingface", "modelscope"}:
        return APIResponseFail(message="source must be huggingface or modelscope")
    if not train_type:
        return APIResponseFail(message="missing train_type")
    try:
        task_id, data = start_model_assets_download_task(train_type, items, source, Path.cwd())
    except Exception as exc:
        return APIResponseFail(message=f"asset download failed to start: {exc}")
    data["message"] = "asset download task started"
    return APIResponseSuccess(data=data)


@router.get("/plugins/musubi/install/log/stream/{task_id}")
async def musubi_install_log_stream(task_id: str):
    """Compatibility alias for plugin install task stdout streams."""
    return await train_log_stream(task_id)


@router.get("/plugins/musubi/install/progress/stream/{task_id}")
async def musubi_install_progress_stream(task_id: str):
    """Server-Sent Events: structured musubi-tuner install progress."""
    if task_id not in tm.tasks:
        raise HTTPException(status_code=404, detail="Unknown task_id")

    async def event_generator():
        idx = 0
        while True:
            await asyncio.sleep(0.08)
            events, total, done = train_log_hub.snapshot_events_from(task_id, idx)
            for event in events:
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            idx = total
            if done:
                yield "data: " + json.dumps({"type": "done", "done": True}, ensure_ascii=False) + "\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/plugins/anima-lora/install")
async def anima_lora_plugin_install(request: Request):
    return await _anima_lora_plugin_install_impl(request, force_install=False)


async def _anima_lora_plugin_install_impl(request: Request, force_install: bool = False):
    if not feature_enabled():
        return _anima_fast_disabled_response()
    payload: dict = json.loads((await request.body()).decode("utf-8") or "{}")
    runtime = _anima_fast_runtime()
    source_commit = str(payload.get("source_commit") or runtime.source_commit or "").strip() or None
    dry_run = payload.get("dry_run", True) is not False
    project_root = Path.cwd()
    layout = default_layout(project_root)
    current_status = read_extension_status(layout)
    if not dry_run and not force_install and current_status.state == STATE_READY:
        return APIResponseSuccess(data={
            "already_ready": True,
            "status": current_status.as_dict(),
            "message": "Anima Fast plugin is already ready",
        })
    explicit = payload.get("source_root") or os.environ.get("ANIMA_LORA_ROOT")
    try:
        source_root = resolve_install_source_root(
            project_root,
            Path(explicit) if explicit else None,
            source_commit,
            allow_clone=False,
        )
    except InstallSourceError as exc:
        return APIResponseFail(message=str(exc))
    plan = build_install_plan(source_root, layout, dry_run=dry_run, source_commit=source_commit)
    data = {"plan": plan.as_dict()}
    if dry_run:
        data["message"] = "Installer dry-run completed"
        return APIResponseSuccess(data=data)
    try:
        from mikazuki.download_sources import parse_download_sources

        task_id, install_data = start_install_task(
            Path.cwd(),
            layout,
            source_root,
            dry_run=False,
            source_commit=source_commit,
            download_sources=parse_download_sources(payload),
        )
    except Exception as exc:
        write_install_state(layout, "broken", {"plan": plan.as_dict()}, str(exc))
        return APIResponseFail(message=f"Anima LoRA install failed: {exc}")
    data.update(install_data)
    data["status"] = read_extension_status(layout).as_dict()
    data["message"] = "Anima LoRA install task started"
    return APIResponseSuccess(data=data)


@router.post("/plugins/anima-lora/repair")
async def anima_lora_plugin_repair(request: Request):
    return await _anima_lora_plugin_install_impl(request, force_install=True)


@router.post("/plugins/anima-lora/uninstall")
async def anima_lora_plugin_uninstall():
    if not feature_enabled():
        return _anima_fast_disabled_response()
    layout = default_layout(Path.cwd())
    try:
        remove_extension(layout, Path.cwd())
    except Exception as exc:
        return APIResponseFail(message=f"Anima LoRA uninstall failed: {exc}")
    return APIResponseSuccess(data={"status": read_extension_status(layout).as_dict()})


@router.post("/anima-fast/preflight")
async def anima_fast_preflight_compat(request: Request):
    return await anima_lora_plugin_preflight(request)


@router.post("/anima-fast/dry-run")
async def anima_fast_dry_run_compat(request: Request):
    return await anima_lora_plugin_dry_run(request)


@router.post("/run_script")
async def run_script(request: Request, background_tasks: BackgroundTasks):
    paras = await request.body()
    j = json.loads(paras.decode("utf-8"))
    script_name = j["script_name"]
    if script_name not in avaliable_scripts:
        return APIResponseFail(message="Script not found")
    del j["script_name"]
    result = []
    for k, v in j.items():
        result.append(f"--{k}")
        if not isinstance(v, bool):
            value = str(v)
            if " " in value:
                value = f'"{v}"'
            result.append(value)
    script_args = " ".join(result)
    script_path = Path(os.getcwd()) / "scripts" / script_name
    cmd = f"{launch_utils.python_bin} {script_path} {script_args}"
    background_tasks.add_task(launch_utils.run, cmd)
    return APIResponseSuccess()


@router.get("/tagger/status")
async def tagger_status():
    return APIResponseSuccess(data=tagger_progress.get())


@router.get("/tagger/download-status")
async def tagger_download_status():
    snap = tagger_progress.get()
    return APIResponseSuccess(data={
        "phase": snap.get("phase"),
        "model": snap.get("model"),
        "download": snap.get("download"),
        "message": snap.get("message"),
        "error": snap.get("error"),
    })


@router.post("/tagger/cancel")
async def tagger_cancel():
    if not tagger_progress.request_cancel():
        return APIResponseSuccess(message="当前无运行中的任务")
    return APIResponseSuccess(message="正在中止任务…")


@router.post("/tagger/reset")
async def tagger_reset():
    if tagger_progress.is_busy():
        tagger_progress.request_cancel()
    tagger_progress.reset_idle("配置参数后点击启动")
    return APIResponseSuccess(message="已重置打标状态")


@router.post("/tagger/prefetch")
async def tagger_prefetch(req: TaggerPrefetchRequest, background_tasks: BackgroundTasks):
    if req.interrogator_model not in available_interrogators:
        return APIResponseFail(message=f"未知模型: {req.interrogator_model}")
    if tagger_progress.is_busy():
        return APIResponseFail(message="已有打标或下载任务进行中")
    background_tasks.add_task(run_prefetch_job, req)
    return APIResponseSuccess(message="模型下载已开始")


@router.post("/interrogate")
async def run_interrogate(req: TaggerInterrogateRequest, background_tasks: BackgroundTasks):
    if req.interrogator_model not in available_interrogators:
        return APIResponseFail(message=f"未知模型: {req.interrogator_model}")
    if tagger_progress.is_busy():
        return APIResponseFail(message="已有打标或下载任务进行中")
    background_tasks.add_task(run_interrogate_job, req)
    return APIResponseSuccess(message="打标任务已提交")


@router.get("/pick_file")
async def pick_file(picker_type: str):
    """Native tkinter picker (desktop host only). Prefer /api/path_browser on Linux/remote."""
    if not path_browser_utils.gui_picker_available():
        return APIResponseFail(
            message="当前环境无法使用系统文件选择框（无桌面 / 远程访问 / 未安装 tkinter）。"
            "请使用网页路径浏览器，或手动输入服务器上的路径。",
            data={"code": "GUI_PICKER_UNAVAILABLE", "web_picker": True},
        )
    if picker_type == "folder":
        coro = asyncio.to_thread(open_directory_selector, "")
    elif picker_type == "model-file":
        file_types = [("checkpoints", "*.safetensors;*.ckpt;*.pt"), ("all files", "*.*")]
        coro = asyncio.to_thread(open_file_selector, "", "Select file", file_types)
    else:
        return APIResponseFail(message=f"不支持的 picker_type: {picker_type}")

    result = await coro
    if result == "":
        return APIResponseFail(message="用户取消选择", data={"code": "CANCELLED", "web_picker": True})

    return APIResponseSuccess(data={
        "path": result
    })


@router.get("/path_browser/capability")
async def path_browser_capability():
    return APIResponseSuccess(data={
        "web_picker": True,
        "gui_picker": path_browser_utils.gui_picker_available(),
        "tkinter": tkinter_available(),
    })


@router.get("/path_browser/list")
async def path_browser_list(
    path: str = "",
    mode: str = "folder",
    name_filter: str = "",
):
    """List a server directory for the in-browser path picker (#244)."""
    try:
        data = await asyncio.to_thread(
            path_browser_utils.list_directory,
            path or None,
            mode=mode,
            name_filter=name_filter or None,
        )
    except PermissionError as exc:
        return APIResponseFail(message=str(exc), data={"code": "DENIED"})
    except FileNotFoundError as exc:
        return APIResponseFail(message=str(exc), data={"code": "NOT_FOUND"})
    except (NotADirectoryError, ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc), data={"code": "BAD_PATH"})
    return APIResponseSuccess(data=data)


@router.get("/get_files")
async def get_files(pick_type) -> APIResponse:
    pick_preset = {
        "model-file": {
            "type": "file",
            "path": "./sd-models",
            "filter": "(.safetensors|.ckpt|.pt)"
        },
        "model-saved-file": {
            "type": "file",
            "path": "./output",
            "filter": "(.safetensors|.ckpt|.pt)"
        },
        "train-dir": {
            "type": "folder",
            "path": "./train",
            "filter": None
        },
    }

    folder_blacklist = [".ipynb_checkpoints", ".DS_Store"]

    def list_path_or_files(preset_info):
        path = Path(preset_info["path"])
        file_type = preset_info["type"]
        regex_filter = preset_info["filter"]
        result_list = []

        if file_type == "file":
            if regex_filter:
                pattern = re.compile(regex_filter)
                files = [f for f in path.glob("**/*") if f.is_file() and pattern.search(f.name)]
            else:
                files = [f for f in path.glob("**/*") if f.is_file()]
            for file in files:
                stat = file.stat()
                result_list.append({
                    "path": str(file.resolve().absolute()).replace("\\", "/"),
                    "name": file.name,
                    "size": f"{round(stat.st_size / (1024**3),2)} GB",
                    "size_bytes": stat.st_size,
                    "mtime": int(stat.st_mtime),
                })
        elif file_type == "folder":
            folders = [f for f in path.iterdir() if f.is_dir()]
            for folder in folders:
                if folder.name in folder_blacklist:
                    continue
                result_list.append({
                    "path": str(folder.resolve().absolute()).replace("\\", "/"),
                    "name": folder.name,
                    "size": 0
                })

        return result_list

    if pick_type not in pick_preset:
        return APIResponseFail(message="Invalid request")

    dirs = list_path_or_files(pick_preset[pick_type])
    return APIResponseSuccess(data={
        "files": dirs
    })


@router.get("/tasks", response_model_exclude_none=True)
async def get_tasks() -> APIResponse:
    return APIResponseSuccess(data={
        "tasks": tm.dump()
    })


@router.get("/tasks/terminate/{task_id}", response_model_exclude_none=True)
async def terminate_task(task_id: str):
    tm.terminate_task(task_id)
    return APIResponseSuccess()


@router.get("/tasks/resume/{task_id}", response_model_exclude_none=True)
async def resume_task(task_id: str):
    """Release a restored queued task that is waiting for manual confirmation."""
    if tm.resume_task(task_id):
        return APIResponseSuccess(data={"resumed": True})
    return APIResponseFail(message="Task is not a held queued task / 任务不在待确认队列中")


@router.get("/tasks/retry/{task_id}", response_model_exclude_none=True)
async def retry_task(task_id: str):
    """Re-queue a finished/failed/terminated training task (stage groups are
    rebuilt as a whole)."""
    new_tasks = tm.retry_task(task_id)
    if not new_tasks:
        return APIResponseFail(message="Task cannot be retried / 任务无法重跑（仅支持已结束的训练任务）")
    return APIResponseSuccess(data={
        "task_id": new_tasks[-1].task_id,
        "task_ids": [t.task_id for t in new_tasks],
        "queued": any(t.status.name == "QUEUED" for t in new_tasks),
    })


@router.get("/tasks/{task_id}/previews", response_model_exclude_none=True)
async def task_previews(task_id: str) -> APIResponse:
    task = tm.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    images = [
        {
            **item,
            "url": f"/api/tasks/{quote(task_id)}/previews/{quote(item['name'])}",
            "thumb_url": f"/api/tasks/{quote(task_id)}/previews/{quote(item['name'])}?thumb=1",
        }
        for item in task_insights.list_preview_images(task.metadata)
    ]
    config = task_insights.resolve_task_config(task.metadata)
    preview_enabled = bool(config.get("sample_prompts")) if config else None
    return APIResponseSuccess(data={"images": images, "preview_enabled": preview_enabled})


@router.get("/tasks/{task_id}/previews/{filename}")
async def task_preview_image(task_id: str, filename: str, thumb: bool = False):
    task = tm.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    path = task_insights.resolve_preview_image(task.metadata, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Unknown preview image")
    headers = {"Cache-Control": "private, max-age=30"}
    if thumb:
        data = task_insights.preview_thumbnail(path)
        if data is not None:
            return Response(content=data, media_type="image/jpeg", headers=headers)
    return FileResponse(path, headers=headers)


@router.get("/tasks/{task_id}/metrics", response_model_exclude_none=True)
async def task_metrics(task_id: str) -> APIResponse:
    task = tm.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    return APIResponseSuccess(data={
        "tags": task_insights.read_loss_scalars(task.metadata),
        "progress": task_insights.read_progress(train_log_hub.tail(task_id, 300)),
    })


@router.get("/graphic_cards")
async def list_avaliable_cards() -> APIResponse:
    if not printable_devices:
        return APIResponse(status="pending")

    return APIResponseSuccess(data={
        "cards": printable_devices
    })


@router.get("/schemas/hashes")
async def list_schema_hashes() -> APIResponse:
    if os.environ.get("MIKAZUKI_SCHEMA_HOT_RELOAD", "0") == "1":
        log.info("Hot reloading schemas")
        await load_schemas()

    return APIResponseSuccess(data={
        "schemas": [
            {
                "name": schema["name"],
                "hash": schema["hash"]
            }
            for schema in avaliable_schemas
        ]
    })


@router.get("/schemas/all")
async def get_all_schemas() -> APIResponse:
    return APIResponseSuccess(data={
        "schemas": avaliable_schemas
    })


@router.get("/presets")
async def get_presets() -> APIResponse:
    if os.environ.get("MIKAZUKI_SCHEMA_HOT_RELOAD", "0") == "1":
        log.info("Hot reloading presets")
        await load_presets()

    return APIResponseSuccess(data={
        "presets": avaliable_presets
    })


@router.get("/config/saved_params")
async def get_saved_params() -> APIResponse:
    saved_params = app_config["saved_params"]
    return APIResponseSuccess(data=saved_params)


@router.get("/train/log/stream/{task_id}")
async def train_log_stream(task_id: str):
    """
    Server-Sent Events: live training stdout (one JSON object per event: {text:...} or {done:true}).
    Open in browser: /train-log?task_id=<uuid>
    """
    if task_id not in tm.tasks:
        raise HTTPException(
            status_code=404,
            detail="Unknown task_id. It is only valid for jobs started in this server session (or the run has not been created).",
        )

    async def event_generator():
        idx = 0
        while True:
            await asyncio.sleep(0.08)
            chunk, total, done = train_log_hub.snapshot_from(task_id, idx)
            for line in chunk:
                yield "data: " + json.dumps({"text": line}, ensure_ascii=False) + "\n\n"
            idx = total
            if done:
                yield "data: " + json.dumps({"done": True}, ensure_ascii=False) + "\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/plugins/anima-lora/install/log/stream/{task_id}")
async def anima_lora_install_log_stream(task_id: str):
    """Compatibility alias for plugin install/train task stdout streams."""
    return await train_log_stream(task_id)


@router.get("/plugins/anima-lora/install/progress/stream/{task_id}")
async def anima_lora_install_progress_stream(task_id: str):
    """Server-Sent Events: structured Anima Fast install progress."""
    if task_id not in tm.tasks:
        raise HTTPException(status_code=404, detail="Unknown task_id")

    async def event_generator():
        idx = 0
        while True:
            await asyncio.sleep(0.08)
            events, total, done = train_log_hub.snapshot_events_from(task_id, idx)
            for event in events:
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            idx = total
            if done:
                yield "data: " + json.dumps({"type": "done", "done": True}, ensure_ascii=False) + "\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/train/log/tail/{task_id}")
async def train_log_tail(task_id: str, limit: int = 240):
    """Recent training stdout lines for the lightweight monitor page."""
    if task_id not in tm.tasks:
        raise HTTPException(status_code=404, detail="Unknown task_id")

    limit = max(1, min(limit, 2000))
    lines, total, done = train_log_hub.snapshot_from(task_id, 0)
    return APIResponseSuccess(data={
        "task_id": task_id,
        "lines": lines[-limit:],
        "total": total,
        "done": done,
    })


@router.get("/train/tasks")
async def list_train_tasks():
    """Running / known training tasks (for tying UI to task_id)."""
    return APIResponseSuccess(data={"tasks": tm.dump()})


@router.get("/check_update")
async def check_update(force: bool = False):
    """Update check against GitHub Releases (stable channel only)."""
    from mikazuki.update_check import get_cached_result, check_update as do_check
    result = None if force else get_cached_result()
    if result is None:
        result = await asyncio.to_thread(do_check, force=force)
    return APIResponseSuccess(data=result)


@router.get("/version")
async def get_version():
    from mikazuki.update_check import local_version
    return APIResponseSuccess(data={"version": local_version()})

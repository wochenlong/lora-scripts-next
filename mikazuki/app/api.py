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

import toml
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse

import mikazuki.process as process
from mikazuki import launch_utils
from mikazuki.app.config import app_config
from mikazuki.app.models import (APIResponse, APIResponseFail,
                                 APIResponseSuccess, TaggerInterrogateRequest)
from mikazuki.log import log
from mikazuki.tagger.interrogator import (available_interrogators,
                                          on_interrogate)
from mikazuki.tasks import tm
from mikazuki.train_log_hub import hub as train_log_hub
from mikazuki.utils import train_utils
from mikazuki.utils.devices import printable_devices
from mikazuki.portable_utils import flash_attn_stack_usable, is_embedded_python
from mikazuki.utils.tk_window import (open_directory_selector,
                                      open_file_selector,
                                      tkinter_available)

router = APIRouter()

ANIMA_TRAIN_TYPES = {"anima-lora", "sd3-lora"}
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
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

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
    "sdxl-lora": "./scripts/stable/sdxl_train_network.py",

    "sd-dreambooth": "./scripts/stable/train_db.py",
    "sdxl-finetune": "./scripts/stable/sdxl_train.py",

    "sd3-lora": "./scripts/dev/anima_train_network.py",
    "anima-lora": "./scripts/dev/anima_train_network.py",
    "flux-lora": "./scripts/dev/flux_train_network.py",
    "flux-finetune": "./scripts/dev/flux_train.py",
}


def _normalize_kv_arg_list(values) -> list[str]:
    """Normalize key=value style arg list from UI payload."""
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


def normalize_custom_args(config: dict) -> None:
    """
    Apply generic arg normalization for all training types.
    - Merge *_custom table input into canonical args list
    - Drop undefined/null entries
    - Keep last value on duplicate keys
    """
    for base_key in ("network_args", "optimizer_args"):
        custom_key = f"{base_key}_custom"
        merged: list[str] = []
        if isinstance(config.get(base_key), list):
            merged.extend(config.get(base_key) or [])
        if isinstance(config.get(custom_key), list):
            merged.extend(config.get(custom_key) or [])

        normalized = _normalize_kv_arg_list(merged)
        if normalized:
            config[base_key] = normalized
        else:
            config.pop(base_key, None)
        config.pop(custom_key, None)


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
    "target_data_dir", "conditioning_data_dir", "dataset_config",
    "output_dir", "logging_dir", "network_weights", "sample_prompts",
    "sample_conditioning_image", "sample_conditioning_image_data_dir",
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
            config[key] = _normalize_kv_arg_list(config[key])
    for key in _PATH_FIELDS:
        if isinstance(config.get(key), str):
            config[key] = config[key].replace("\\", "/")


async def load_schemas():
    avaliable_schemas.clear()

    schema_dir = os.path.join(os.getcwd(), "mikazuki", "schema")
    schemas = os.listdir(schema_dir)

    def lambda_hash(x):
        return hashlib.md5(x.encode()).hexdigest()

    for schema_name in schemas:
        with open(os.path.join(schema_dir, schema_name), encoding="utf-8") as f:
            content = f.read()
            avaliable_schemas.append({
                "name": schema_name.rstrip(".ts"),
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


def get_sample_prompts(config: dict, model_train_type: str = "sd-lora") -> Tuple[Optional[str], str, Optional[str]]:
    # backward compatibility
    if "sample_prompts" in config and "positive_prompts" not in config:
        return None, config["sample_prompts"], None

    train_data_dir = config["train_data_dir"]
    sub_dir = [dir for dir in glob(os.path.join(train_data_dir, '*')) if os.path.isdir(dir)]

    use_anima_defaults = model_train_type in ANIMA_TRAIN_TYPES and is_preview_enabled(config)
    use_conditioning_preview = is_conditioning_preview_enabled(config, model_train_type)
    default_positive = ANIMA_DEFAULT_SAMPLE_POSITIVE if use_anima_defaults else None
    default_negative = ANIMA_DEFAULT_SAMPLE_NEGATIVE if use_anima_defaults else ''
    default_width = 1024 if use_anima_defaults else 512
    default_height = 1024 if use_anima_defaults else 512
    default_cfg = 4.5 if use_anima_defaults else 7
    default_seed = 42 if use_anima_defaults else 2333
    default_steps = 40 if use_anima_defaults else 24

    positive_prompts = config.pop('positive_prompts', default_positive)
    negative_prompts = config.pop('negative_prompts', default_negative)
    sample_width = config.pop('sample_width', default_width)
    sample_height = config.pop('sample_height', default_height)
    sample_cfg = config.pop('sample_cfg', default_cfg)
    sample_seed = config.pop('sample_seed', default_seed)
    sample_steps = config.pop('sample_steps', default_steps)
    randomly_choice_prompt = config.pop('randomly_choice_prompt', False)
    conditioning_preview_prompt = config.pop("conditioning_preview_prompt", None)
    sample_conditioning_image = config.pop("sample_conditioning_image", None)
    random_conditioning_preview_image = config.pop("random_conditioning_preview_image", False)
    sample_conditioning_image_data_dir = config.pop("sample_conditioning_image_data_dir", None)

    if randomly_choice_prompt:
        if len(sub_dir) != 1:
            raise ValueError('训练数据集下有多个子文件夹，无法启用随机选取 Prompt 功能')

        txt_files = glob(os.path.join(sub_dir[0], '*.txt'))
        if not txt_files:
            raise ValueError('训练数据集路径没有 txt 文件')
        try:
            sample_prompt_file = random.choice(txt_files)
            with open(sample_prompt_file, 'r', encoding='utf-8') as f:
                positive_prompts = f.read()
        except IOError:
            log.error(f"读取 {sample_prompt_file} 文件失败")

    control_image_arg = ""
    selected_control_image = None
    if use_conditioning_preview:
        positive_prompts = conditioning_preview_prompt or positive_prompts
        control_image = None
        if _truthy(random_conditioning_preview_image):
            random_images = _image_files(str(sample_conditioning_image_data_dir or ""))
            if not random_images:
                raise ValueError("已启用随机 Control Image，但随机目录没有可用图片。")
            control_image = random.choice(random_images)
        elif sample_conditioning_image:
            control_image = str(sample_conditioning_image)

        if not control_image or not os.path.isfile(control_image):
            raise ValueError("已启用图像编辑预览，请选择固定 Control Image 或配置随机目录。")
        selected_control_image = _normalize_path(control_image)
        control_image_arg = f" --cn {_normalize_path(control_image)}"

    return positive_prompts, f'{positive_prompts} --n {negative_prompts}  --w {sample_width} --h {sample_height} --l {sample_cfg}  --s {sample_steps}  --d {sample_seed}{control_image_arg}', selected_control_image


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
    return config.get("enable_preview") in (True, "true", "True", "1", 1)


def _truthy(value) -> bool:
    return value in (True, "true", "True", "1", 1)


def is_conditioning_enabled(config: dict, model_train_type: str) -> bool:
    return model_train_type in ANIMA_TRAIN_TYPES and _truthy(config.get("conditioning"))


def is_conditioning_preview_enabled(config: dict, model_train_type: str) -> bool:
    return is_conditioning_enabled(config, model_train_type) and _truthy(config.get("enable_conditioning_preview"))


def _image_files(path: str, recursive: bool = False) -> list[str]:
    if not path or not os.path.isdir(path):
        return []
    pattern = "**/*" if recursive else "*"
    return [
        file
        for file in glob(os.path.join(path, pattern), recursive=recursive)
        if os.path.isfile(file) and file.lower().endswith(IMAGE_EXTENSIONS)
    ]


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _dataset_resolution(value):
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple)):
        return [int(item) for item in value]

    text = str(value or "").strip()
    if not text:
        return [1024, 1024]
    for separator in (",", "x", "X", "*"):
        if separator in text:
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) == 2:
                return [int(parts[0]), int(parts[1])]
    return int(text)


def _prepare_conditioning_dataset_config(config: dict, autosave_dir: str, timestamp: str) -> Optional[str]:
    target_data_dir = str(config.pop("target_data_dir", "") or "").strip()
    conditioning_data_dir = str(config.pop("conditioning_data_dir", "") or "").strip()

    if not target_data_dir:
        raise ValueError("启用图像编辑训练后，请填写目标图目录 Target。")
    if not conditioning_data_dir:
        raise ValueError("启用图像编辑训练后，请填写参考图目录 Reference / Conditioning。")
    if not os.path.isdir(target_data_dir):
        raise ValueError(f"目标图目录不存在: {target_data_dir}")
    if not os.path.isdir(conditioning_data_dir):
        raise ValueError(f"参考图目录不存在: {conditioning_data_dir}")
    if not _image_files(target_data_dir):
        raise ValueError("目标图目录没有可训练图片，请检查 Target。")
    if not _image_files(conditioning_data_dir):
        raise ValueError("参考图目录没有可用图片，请检查 Reference / Conditioning。")

    config["train_data_dir"] = target_data_dir
    dataset_config = {
        "general": {
            "caption_extension": config.get("caption_extension", ".txt"),
        },
        "datasets": [
            {
                "resolution": _dataset_resolution(config.get("resolution", "1024,1024")),
                "batch_size": int(config.get("train_batch_size", 1)),
                "enable_bucket": bool(config.get("enable_bucket", True)),
                "subsets": [
                    {
                        "image_dir": _normalize_path(target_data_dir),
                        "conditioning_data_dir": _normalize_path(conditioning_data_dir),
                    }
                ],
            }
        ],
    }

    for key in ("min_bucket_reso", "max_bucket_reso", "bucket_reso_steps"):
        if config.get(key) is not None:
            dataset_config["datasets"][0][key] = int(config[key])

    dataset_config_file = os.path.join(autosave_dir, f"{timestamp}-dataset.toml")
    with open(dataset_config_file, "w", encoding="utf-8") as f:
        f.write(toml.dumps(dataset_config))

    config["conditioning"] = True
    config["dataset_config"] = dataset_config_file
    log.info(f"Wrote conditioning dataset config to {dataset_config_file}")
    return dataset_config_file


def _detect_best_attn_mode() -> str:
    """Auto-detect the best available attention backend for Anima training."""
    if not is_embedded_python() and flash_attn_stack_usable():
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


def apply_anima_training_defaults(config: dict, model_train_type: str):
    if model_train_type not in ANIMA_TRAIN_TYPES:
        return

    if str(config.get("unet_lr", "")).strip() in ANIMA_LEGACY_UNET_LR:
        config["unet_lr"] = ANIMA_DEFAULT_UNET_LR
    elif isinstance(config.get("unet_lr"), str):
        config["unet_lr"] = float(config["unet_lr"])

    if is_conditioning_enabled(config, model_train_type):
        config["sample_at_first"] = False
        config["cache_latents"] = True
        config["cache_text_encoder_outputs"] = True
    elif is_preview_enabled(config) or config.get("sample_prompts"):
        config["sample_at_first"] = True

    optimizer_type = str(config.get("optimizer_type", "")).strip().lower()
    if optimizer_type in ANIMA_FULL_PRECISION_UNSAFE_OPTIMIZERS:
        if config.get("mixed_precision") == "fp16" and _cuda_bf16_supported():
            config["mixed_precision"] = "bf16"
            log.warning(
                "Changed Anima mixed_precision from fp16 to bf16 for optimizer "
                f"{config.get('optimizer_type')}. fp16 is more likely to produce loss=nan."
            )

        disabled = []
        for key in ("full_bf16", "full_fp16"):
            if config.pop(key, None):
                disabled.append(key)
        if disabled:
            log.warning(
                "Disabled Anima full half-precision training for optimizer "
                f"{config.get('optimizer_type')} ({', '.join(disabled)}). "
                "This keeps trainable LoRA weights in fp32 to reduce loss=nan risk."
            )

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
        if is_embedded_python() or not flash_attn_stack_usable():
            best = _detect_best_attn_mode()
            config["attn_mode"] = best
            log.warning(
                f"attn_mode='flash' requested but flash-attn is not available, "
                f"falling back to '{best}'"
            )


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

    gpu_ids = config.pop("gpu_ids", None)

    model_train_type = config.pop("model_train_type", "sd-lora")
    trainer_file = trainer_mapping[model_train_type]
    try:
        if is_conditioning_enabled(config, model_train_type):
            _prepare_conditioning_dataset_config(config, autosave_dir, timestamp)
    except ValueError as e:
        log.error(f"Error while processing conditioning dataset: {e}")
        return APIResponseFail(message=str(e))

    suggest_cpu_threads = 8 if len(train_utils.get_total_images(config["train_data_dir"])) > 200 else 2
    apply_sdxl_prediction_type(config, model_train_type)
    apply_anima_training_defaults(config, model_train_type)

    if model_train_type != "sdxl-finetune":
        if is_conditioning_enabled(config, model_train_type):
            if not _image_files(config["train_data_dir"]):
                return APIResponseFail(message="目标图目录没有可训练图片，请检查 Target。")
        elif not train_utils.validate_data_dir(config["train_data_dir"]):
            return APIResponseFail(message="训练数据集路径不存在或没有图片，请检查目录。")

    validated, message = train_utils.validate_model(config["pretrained_model_name_or_path"], model_train_type)
    if not validated:
        return APIResponseFail(message=message)

    selected_conditioning_preview_image = None
    if "prompt_file" in config and config["prompt_file"].strip() != "":
        prompt_file = config["prompt_file"].strip()
        if not os.path.exists(prompt_file):
            return APIResponseFail(message=f"Prompt 文件 {prompt_file} 不存在，请检查路径。")
        config["sample_prompts"] = prompt_file
    else:
        try:
            positive_prompt, sample_prompts_arg, selected_conditioning_preview_image = get_sample_prompts(config=config, model_train_type=model_train_type)

            if positive_prompt is not None and train_utils.is_promopt_like(sample_prompts_arg):
                sample_prompts_file = os.path.join(autosave_dir, f"{timestamp}-promopt.txt")
                with open(sample_prompts_file, "w", encoding="utf-8") as f:
                    f.write(sample_prompts_arg)
                config["sample_prompts"] = sample_prompts_file
                log.info(f"Wrote prompts to file {sample_prompts_file}")

        except ValueError as e:
            log.error(f"Error while processing prompts: {e}")
            return APIResponseFail(message=str(e))

    apply_anima_training_defaults(config, model_train_type)
    sanitize_config(config)

    if not config.get("sample_prompts"):
        config.pop("sample_at_first", None)
        config.pop("sample_every_n_epochs", None)
        config.pop("sample_every_n_steps", None)

    with open(toml_file, "w", encoding="utf-8") as f:
        f.write(toml.dumps(config))

    if selected_conditioning_preview_image:
        monitor_metadata_file = f"{toml_file}.monitor.json"
        with open(monitor_metadata_file, "w", encoding="utf-8") as f:
            json.dump(
                {"conditioning_reference_image": selected_conditioning_preview_image},
                f,
                ensure_ascii=False,
                indent=2,
            )

    result = process.run_train(toml_file, trainer_file, gpu_ids, suggest_cpu_threads)

    return result


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


@router.post("/interrogate")
async def run_interrogate(req: TaggerInterrogateRequest, background_tasks: BackgroundTasks):
    interrogator = available_interrogators.get(req.interrogator_model, available_interrogators["wd14-convnextv2-v2"])
    background_tasks.add_task(
        on_interrogate,
        image=None,
        batch_input_glob=req.path,
        batch_input_recursive=req.batch_input_recursive,
        batch_output_dir="",
        batch_output_filename_format="[name].[output_extension]",
        batch_output_action_on_conflict=req.batch_output_action_on_conflict,
        batch_remove_duplicated_tag=True,
        batch_output_save_json=False,
        interrogator=interrogator,
        threshold=req.threshold,
        character_threshold=req.character_threshold,
        add_rating_tag=req.add_rating_tag,
        add_model_tag=req.add_model_tag,
        additional_tags=req.additional_tags,
        exclude_tags=req.exclude_tags,
        sort_by_alphabetical_order=False,
        add_confident_as_weight=False,
        replace_underscore=req.replace_underscore,
        replace_underscore_excludes=req.replace_underscore_excludes,
        escape_tag=req.escape_tag,
        unload_model_after_running=True
    )
    return APIResponseSuccess()


@router.get("/pick_file")
async def pick_file(picker_type: str):
    if not tkinter_available():
        return APIResponseFail(
            message="当前环境未安装 tkinter，无法弹出系统文件夹/文件选择框。"
            "请手动输入路径；整合包用户请使用已打包 tkinter 的版本或重新运行 build_portable.ps1。"
        )
    if picker_type == "folder":
        coro = asyncio.to_thread(open_directory_selector, "")
    elif picker_type == "model-file":
        file_types = [("checkpoints", "*.safetensors;*.ckpt;*.pt"), ("all files", "*.*")]
        coro = asyncio.to_thread(open_file_selector, "", "Select file", file_types)
    elif picker_type == "image-file":
        file_types = [("images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"), ("all files", "*.*")]
        coro = asyncio.to_thread(open_file_selector, "", "Select image", file_types)
    else:
        return APIResponseFail(message=f"不支持的 picker_type: {picker_type}")

    result = await coro
    if result == "":
        return APIResponseFail(message="用户取消选择")

    return APIResponseSuccess(data={
        "path": result
    })


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
        "image-file": {
            "type": "file",
            "path": "./train",
            "filter": "(.png|.jpg|.jpeg|.webp|.bmp)"
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
async def check_update():
    """Non-blocking update check against GitHub Releases."""
    from mikazuki.update_check import get_cached_result, check_update as do_check
    result = get_cached_result()
    if result is None:
        result = await asyncio.to_thread(do_check)
    return APIResponseSuccess(data=result)


@router.get("/version")
async def get_version():
    from mikazuki.update_check import local_version
    return APIResponseSuccess(data={"version": local_version()})

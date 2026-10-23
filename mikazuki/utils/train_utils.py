from enum import Enum
import glob
import os
import re
import shutil
import sys
import json
from typing import Dict, Optional

import toml

from mikazuki.log import log

python_bin = sys.executable

PREVIEW_UI_FIELDS = (
    "positive_prompts",
    "negative_prompts",
    "sample_width",
    "sample_height",
    "sample_cfg",
    "sample_seed",
    "sample_steps",
    "sample_sampler",
    "randomly_choice_prompt",
    "sample_at_first",
    "sample_every_n_epochs",
    "sample_every_n_steps",
    "prompt_file",
)

PREVIEW_ENABLE_TEXT_FIELDS = (
    "sample_prompts",
    "positive_prompts",
    "negative_prompts",
)

PREVIEW_ENABLE_INTERVAL_FIELDS = (
    "sample_every_n_epochs",
    "sample_every_n_steps",
)


class ModelType(Enum):
    UNKNOWN = -1
    SD15 = 1
    SD2 = 2
    SDXL = 3
    SD3 = 4
    FLUX = 5
    LUMINA = 6
    LoRA = 10


MODEL_SIGNATURE = [
    {
        "type": ModelType.LUMINA,
        "signature": [
            "cap_embedder.0.weight",
            "context_refiner.0.attention.k_norm.weight",
        ]
    },
    {
        "type": ModelType.FLUX,
        "signature": [
            "double_blocks.0.img_mlp.0.weight",
            "guidance_in.in_layer.weight"
            "model.diffusion_model.double_blocks",
            "double_blocks.0.img_attn.norm.query_norm.scale",
        ]
    },
    {
        "type": ModelType.SD3,
        "signature": [
            "model.diffusion_model.x_embedder.proj.weight",
            "model.diffusion_model.joint_blocks.0.context_block.attn.proj.weight"
        ]
    },
    {
        "type": ModelType.SDXL,
        "signature": [
            "conditioner.embedders.1.model.transformer.resblocks",
        ]
    },
    {
        "type": ModelType.SD15,
        "signature": [
            "model.diffusion_model",
            "cond_stage_model.transformer.text_model",
        ]
    },
    {
        "type": ModelType.LoRA,
        "signature": [
            "lora_te_text_model_encoder",
            "lora_unet_up_blocks"
            "lora_unet_input_blocks_4_1_transformer_blocks_0_attn1_to_k.alpha",
            "lora_unet_input_blocks_4_1_transformer_blocks_0_attn1_to_k.lora_up.weight",

            # more common signature
            "lora_unet",
            "lora_te",
            "lora_A.weight",
        ]
    }
]


def is_promopt_like(s):
    for p in ["--n", "--s", "--l", "--d"]:
        if p in s:
            return True
    return False


def _has_non_empty_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _positive_int_value(value) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def has_preview_enable_signal(config: dict) -> bool:
    """Return true when preview-only prompt/schedule fields indicate intent.

    This is a transition guard for schemastery serialization dropping or
    falsifying the ``enable_preview`` discriminator while keeping the preview
    branch payload. Keep the signal set strict: prompts or sampling interval
    only, not generic UI defaults like sampler or sample_at_first.
    """
    if any(_has_non_empty_value(config.get(key)) for key in PREVIEW_ENABLE_TEXT_FIELDS):
        return True
    return any(_positive_int_value(config.get(key)) for key in PREVIEW_ENABLE_INTERVAL_FIELDS)


def is_preview_enabled(config: dict) -> bool:
    return config.get("enable_preview") in (True, "true", "True", "1", 1) or has_preview_enable_signal(config)


def ensure_enable_preview_flag(config: dict) -> None:
    # Kohaku uses its native SAMPLE_* fields, not Kohya's preview switch.
    if config.get("model_train_type") == "kohaku-moss-image-lora":
        return
    if has_preview_enable_signal(config):
        config["enable_preview"] = True


def has_explicit_sample_prompt_source(config: dict) -> bool:
    prompt_file = str(config.get("prompt_file") or "").strip()
    if prompt_file:
        return True
    sample_prompts = str(config.get("sample_prompts") or "").strip()
    return bool(sample_prompts)


def should_generate_sample_prompts(config: dict) -> bool:
    return is_preview_enabled(config) or has_explicit_sample_prompt_source(config)


def strip_disabled_preview_fields(config: dict) -> None:
    for key in PREVIEW_UI_FIELDS:
        config.pop(key, None)


def normalize_sample_prompt_text(text: str) -> str:
    """Collapse user-entered prompt fields to a single Kohya prompt line."""
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text).replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")).strip()


def build_sample_prompt_line(
    positive: str,
    negative: str,
    *,
    width: int = 512,
    height: int = 512,
    cfg: float = 7.0,
    steps: int = 24,
    seed: int = 2333,
    sampler: str | None = None,
) -> str:
    positive = normalize_sample_prompt_text(positive)
    negative = normalize_sample_prompt_text(negative)
    line = (
        f"{positive} --n {negative} --w {width} --h {height} "
        f"--l {cfg} --s {steps} --d {seed}"
    )
    if sampler:
        line += f" --ss {normalize_sample_prompt_text(sampler)}"
    return line


def is_broken_multiline_sample_prompt(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    first = lines[0]
    if any(token in first for token in (" --n", " --w", " --h", " --l", " --s", " --d")):
        return False
    rest = " ".join(lines[1:])
    lowered = rest.lower()
    return lowered.startswith("--n") or lowered.startswith("n ") or " --n" in lowered


def normalize_sample_prompt_file_content(content: str) -> str:
    lines = [
        line.strip()
        for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip() and not line.strip().startswith("#")
    ]
    if not lines:
        return ""
    if len(lines) == 1:
        return normalize_sample_prompt_text(lines[0])
    if is_broken_multiline_sample_prompt(lines):
        return normalize_sample_prompt_text(" ".join(lines))
    return "\n".join(normalize_sample_prompt_text(line) for line in lines)


def normalize_sample_prompt_file(path: str) -> str:
    prompt_path = os.path.abspath(path)
    if not os.path.isfile(prompt_path):
        return ""
    with open(prompt_path, "r", encoding="utf-8") as handle:
        original = handle.read()
    normalized = normalize_sample_prompt_file_content(original)
    if normalized != original.strip() and "\n" not in normalized:
        with open(prompt_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(normalized + "\n")
        log.info(f"Normalized sample prompt file to single line: {prompt_path}")
    return normalized


def match_model_type_legacy(sig_content: bytes):
    if b"model.diffusion_model.double_blocks" in sig_content or b"double_blocks.0.img_attn.norm.query_norm.scale" in sig_content:
        return ModelType.FLUX

    if b"model.diffusion_model.x_embedder.proj.weight" in sig_content:
        return ModelType.SD3

    if b"conditioner.embedders.1.model.transformer.resblocks" in sig_content:
        return ModelType.SDXL

    if b"model.diffusion_model" in sig_content or b"cond_stage_model.transformer.text_model" in sig_content:
        return ModelType.SD15

    if b"lora_unet" in sig_content or b"lora_te" in sig_content:
        return ModelType.LoRA

    return ModelType.UNKNOWN


def read_safetensors_metadata(path) -> Dict:
    if not os.path.exists(path):
        log.error(f"Can't find safetensors metadata file {path}")
        return None

    with open(path, "rb") as f:
        meta_length = int.from_bytes(f.read(8), "little")
        meta = f.read(meta_length)
        return json.loads(meta)


# vendor/sd-scripts/library/anima_utils.py builds the Anima DiT with num_blocks=28;
# a 2.9B checkpoint carries more blocks and can only be trained by Anima Fast (#408).
KOHYA_ANIMA_MAX_BLOCKS = 28


def anima_checkpoint_block_count(path) -> Optional[int]:
    """DiT block count from a safetensors header, or None when unreadable / not Anima.

    Reads only the JSON header: cheap, and never loads weights or touches the GPU.
    """
    try:
        metadata = read_safetensors_metadata(path)
    except Exception:  # noqa: BLE001 - a broken header simply means "cannot tell"
        return None
    if not isinstance(metadata, dict):
        return None
    highest = None
    for key in metadata:
        if not isinstance(key, str):
            continue
        match = re.match(r"^blocks\.(\d+)\.", key)
        if match is None:
            continue
        index = int(match.group(1))
        if highest is None or index > highest:
            highest = index
    return None if highest is None else highest + 1


def guess_model_type(path):
    if path.endswith("safetensors"):
        metadata = read_safetensors_metadata(path)
        model_keys = "\n".join(metadata.keys())
        for m in MODEL_SIGNATURE:
            if any([k in model_keys for k in m["signature"]]):
                return m["type"]

        return ModelType.UNKNOWN

    if path.endswith("pt") or path.endswith("ckpt"):
        with open(path, "rb") as f:
            content = f.read(1024 * 1000)
            return match_model_type_legacy(content)


def validate_model(model_name: str, training_type: str = "sd-lora"):
    if training_type in ["anima-lora", "sd3-lora", "anima-finetune"]:
        # vendor/sd-scripts/library/anima_utils.py hardcodes num_blocks=28, so an
        # Anima 2.9B checkpoint only fails later with a wall of "Unexpected keys ...
        # blocks.28.*" names. Detect it from the safetensors header (no weights, no
        # GPU) and point the user at the engine that supports it (#408).
        if os.path.isfile(model_name) and str(model_name).lower().endswith(".safetensors"):
            try:
                blocks = anima_checkpoint_block_count(model_name)
            except Exception as exc:  # noqa: BLE001 - unreadable headers surface in the trainer
                log.warning(f"Can't inspect model file {model_name}: {exc}")
                blocks = None
            if blocks is not None and blocks > KOHYA_ANIMA_MAX_BLOCKS:
                return False, (
                    f"检测到 Anima 2.9B 底模（{blocks} 个 block），Kohya 引擎不支持该规格。"
                    "请改用 Anima Fast 引擎（可在「设置 → 训练引擎」中安装），或改用 Anima 2B 底模。"
                )
        return True, "ok"

    if os.path.exists(model_name):
        if os.path.isdir(model_name):
            files = os.listdir(model_name)
            if "model_index.json" in files or "unet" in model_name:
                return True, "ok"
            else:
                log.warning("Can't find model, is this a huggingface model folder?")
                return True, "ok"

        model_type = ModelType.UNKNOWN

        try:
            model_type = guess_model_type(model_name)
        except Exception as e:
            log.warning(f"model file {model_name} can't open: {e}")
            return True, ""

        if model_type == ModelType.UNKNOWN:
            log.error(f"Can't match model type from {model_name}")

        if model_type not in [ModelType.SD15, ModelType.SD2, ModelType.SD3, ModelType.SDXL, ModelType.FLUX, ModelType.LUMINA]:
            return False, "Pretrained model is not a Stable Diffusion, Flux or Lumina checkpoint / 校验失败：底模不是 Stable Diffusion, Flux 或 Lumina 模型"

        if model_type == ModelType.SDXL and training_type == "sd-lora":
            return False, "Pretrained model is SDXL, but you are training with SD1.5 LoRA / 校验失败：你选择的是 SD1.5 LoRA 训练，但预训练模型是 SDXL。请前往专家模式选择正确的模型种类。"

        return True, "ok"

    # huggingface model repo
    if model_name.count("/") == 1 \
            and not model_name[0] in [".", "/"] \
            and not model_name.split(".")[-1] in ["pt", "pth", "ckpt", "safetensors"]:
        return True, "ok"

    return False, "model not found"


def validate_data_dir(path, auto_organize=True):
    """Check that ``path`` can act as a kohya-style dataset root.

    When no ``N_xxx`` subdirectory exists and ``auto_organize`` is set, loose
    images are moved into a generated one. Pass ``auto_organize=False`` whenever
    something else owns the dataset layout (a ``dataset_config`` toml): moving
    files would leave its ``image_dir`` entries pointing at emptied directories.
    """
    if not os.path.exists(path):
        log.error(f"Data dir {path} not exists, check your params")
        return False

    dir_content = os.listdir(path)

    if len(dir_content) == 0:
        log.error(f"Data dir {path} is empty, check your params")

    subdirs = [f for f in dir_content if os.path.isdir(os.path.join(path, f))]

    if len(subdirs) == 0:
        log.warning(f"No subdir found in data dir")

    ok_dir = [d for d in subdirs if re.findall(r"^\d+_.+", d)]

    if len(ok_dir) > 0:
        log.info(f"Found {len(ok_dir)} legal dataset")
        return True

    if not auto_organize:
        if get_total_images(path, True):
            log.info(f"Data dir {path} has no N_xxx subdir; leaving layout to the dataset config")
            return True
        log.error("No image found in data dir")
        return False

    log.warning(f"No leagal dataset found. Try find avaliable images")
    imgs = get_total_images(path, False)
    captions = glob.glob(path + '/*.txt')
    log.info(f"{len(imgs)} images found, {len(captions)} captions found")
    if len(imgs) > 0:
        num_repeat = suggest_num_repeat(len(imgs))
        dataset_path = os.path.join(path, f"{num_repeat}_zkz")
        os.makedirs(dataset_path)
        for i in imgs:
            shutil.move(i, dataset_path)
        if len(captions) > 0:
            for c in captions:
                shutil.move(c, dataset_path)
        log.warning(
            f"Auto dataset created: moved {len(imgs)} images and {len(captions)} captions "
            f"into {dataset_path} / 已把 {len(imgs)} 张图片与 {len(captions)} 个标签文件移动到 {dataset_path}"
        )
    else:
        log.error("No image found in data dir")
        return False

    return True


# Mirror sd-scripts' library/train_util.py IMAGE_EXTENSIONS. Using our narrower
# jpg/jpeg/png set here would reject a valid .webp dataset.
DATASET_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def count_subset_images(image_dir):
    """Count images the way sd-scripts' ``glob_images`` does: non-recursively."""
    if not os.path.isdir(image_dir):
        return 0
    total = 0
    for entry in os.scandir(image_dir):
        if entry.is_file() and os.path.splitext(entry.name)[1].lower() in DATASET_IMAGE_EXTENSIONS:
            total += 1
    return total


def _describe_subset_dir(image_dir, config_dir):
    """Return None when the subset is usable, else why sd-scripts will skip it.

    Relative paths are resolved exactly as sd-scripts does -- as given, i.e.
    against the training process' working directory -- because resolving them
    more generously here would let the preflight pass on a subset that training
    still skips, which is the whole failure we are trying to catch.
    """
    if not os.path.isdir(image_dir):
        if not os.path.isabs(image_dir) and count_subset_images(os.path.join(config_dir, image_dir)) > 0:
            return "目录不存在 / missing（相对路径按训练器工作目录解析，请改用绝对路径）"
        return "目录不存在 / missing"

    if count_subset_images(image_dir) == 0:
        if not os.path.isabs(image_dir) and count_subset_images(os.path.join(config_dir, image_dir)) > 0:
            return "目录里没有图片 / no images（相对路径按训练器工作目录解析，请改用绝对路径）"
        return "目录里没有图片 / no images"

    return None


def validate_dataset_config(dataset_config):
    """Reject a dataset toml whose subsets sd-scripts would silently skip.

    sd-scripts logs a single warning per skipped subset and then trains on
    whatever subsets are left, so a wrong ``image_dir``, a ``num_repeats``
    below 1, or a duplicated ``image_dir`` / ``metadata_file`` produces a run
    that completes normally, emits checkpoints, and quietly trained on a
    fraction of the data. Fail the submit instead.

    Returns ``(ok, message)``.
    """
    config_path = os.path.abspath(str(dataset_config).strip())
    if not os.path.isfile(config_path):
        return False, f"数据集配置文件不存在 / dataset_config not found: {dataset_config}"

    try:
        parsed = toml.load(config_path)
    except Exception as e:
        return False, f"数据集配置文件解析失败 / cannot parse dataset_config: {dataset_config} ({e})"

    subsets = []
    datasets = parsed.get("datasets")
    if isinstance(datasets, list):
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            entries = dataset.get("subsets")
            if isinstance(entries, list):
                subsets.extend(s for s in entries if isinstance(s, dict))

    if not subsets:
        return False, (
            f"数据集配置里没有任何 [[datasets.subsets]] / no dataset subsets defined: {dataset_config}"
        )

    config_dir = os.path.dirname(config_path)
    problems = []
    checked = 0
    seen_keys = set()
    for index, subset in enumerate(subsets, 1):
        image_dir = str(subset.get("image_dir") or "").strip()
        metadata_file = str(subset.get("metadata_file") or "").strip()
        key = image_dir or metadata_file
        label = key or f"第 {index} 个子集 / subset #{index}"

        # sd-scripts checks num_repeats first and registers only surviving
        # subsets (train_util.py prepare_images), so a subset skipped here
        # cannot shadow a later duplicate of itself. Omitting num_repeats
        # defaults to 1 (config_util.py BaseSubsetParams); a non-int value
        # already fails the toml schema check, so only int < 1 skips silently.
        num_repeats = subset.get("num_repeats")
        if isinstance(num_repeats, int) and num_repeats < 1:
            problems.append(f"{label}（num_repeats={num_repeats} 小于 1，sd-scripts 会忽略整个子集）")
            continue

        if key:
            if key in seen_keys:
                problems.append(f"{label}（重复子集，sd-scripts 只保留第一个 / duplicated subset is ignored）")
                continue
            seen_keys.add(key)

        if not image_dir:
            # metadata_file-driven finetune subsets carry their own image list.
            continue
        checked += 1
        problem = _describe_subset_dir(image_dir, config_dir)
        if problem:
            problems.append(f"{image_dir}（{problem}）")

    if problems:
        listed = "\n".join(f"  - {item}" for item in problems)
        return False, (
            "数据集配置中以下子集会被 sd-scripts 静默跳过，训练看起来正常但这部分数据不会被训练：\n"
            f"{listed}\n"
            "请检查 dataset_config。注意 sd-scripts 只扫描该目录下的图片，不递归子目录；"
            "num_repeats 必须 ≥1；重复的 image_dir / metadata_file 只保留第一个。"
        )

    log.info(f"Dataset config {config_path} validated: {checked} image subset(s) have images")
    return True, "ok"


def suggest_num_repeat(img_count):
    if img_count <= 10:
        return 7
    elif 10 < img_count <= 50:
        return 5
    elif 50 < img_count <= 100:
        return 3

    return 1


def check_training_params(data):
    potential_path = [
        "train_data_dir", "reg_data_dir", "output_dir"
    ]
    file_paths = [
        "sample_prompts"
    ]
    for p in potential_path:
        if p in data and not os.path.exists(data[p]):
            return False

    for f in file_paths:
        if f in data and not os.path.exists(data[f]):
            return False
    return True


def get_total_images(path, recursive=True, limit=None):
    if limit is not None:
        limit = int(limit)
        if limit <= 0:
            return []
        if not os.path.isdir(path):
            return []
        image_files = []
        image_suffixes = {".jpg", ".jpeg", ".png"}
        if recursive:
            for root, _, files in os.walk(path):
                for name in files:
                    if os.path.splitext(name)[1].lower() not in image_suffixes:
                        continue
                    image_files.append(os.path.join(root, name))
                    if len(image_files) >= limit:
                        return image_files
        else:
            for entry in os.scandir(path):
                if not entry.is_file():
                    continue
                if os.path.splitext(entry.name)[1].lower() not in image_suffixes:
                    continue
                image_files.append(entry.path)
                if len(image_files) >= limit:
                    return image_files
        return image_files

    if recursive:
        image_files = glob.glob(path + '/**/*.jpg', recursive=True)
        image_files += glob.glob(path + '/**/*.jpeg', recursive=True)
        image_files += glob.glob(path + '/**/*.png', recursive=True)
    else:
        image_files = glob.glob(path + '/*.jpg')
        image_files += glob.glob(path + '/*.jpeg')
        image_files += glob.glob(path + '/*.png')
    return image_files


def fix_config_types(config: dict):
    keep_float_params = ["guidance_scale", "sigmoid_scale", "discrete_flow_shift"]
    for k in keep_float_params:
        if k in config:
            config[k] = float(config[k])

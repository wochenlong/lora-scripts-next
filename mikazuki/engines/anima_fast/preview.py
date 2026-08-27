from __future__ import annotations

from glob import glob
from pathlib import Path
import os
import random

from .adapter import AdapterError, int_value, is_empty
from mikazuki.utils.train_utils import (
    build_sample_prompt_line as build_kohya_sample_prompt_line,
    is_preview_enabled as shared_is_preview_enabled,
)

DEFAULT_SAMPLE_POSITIVE = (
    "1girl, solo, smile, japanese clothes, kimono, blue eyes, closed mouth, upper body, looki"
    "ng at viewer, hair ornament, long hair, yellow kimono, black hair, anime coloring, yukat"
    "a, choker, split mouth, side ponytail, bow, brown hair"
)
DEFAULT_SAMPLE_NEGATIVE = (
    "nsfw, explicit, sexual content, nude, naked, nipples, areola, genitals, cleavage, breast"
    "s, ass, buttocks, thighs, underwear, lingerie, bikini, swimsuit, erotic, suggestive, lew"
    "d, spread legs, close-up body, transparent clothes, worst quality, low quality, score_1,"
    " score_2, score_3, artist name, jpeg artifacts"
)


def is_preview_enabled(config: dict) -> bool:
    return shared_is_preview_enabled(config) or not is_empty(config.get("prompt_file"))


def _strip_preview_fields(config: dict) -> None:
    for key in (
        "sample_prompts",
        "sample_at_first",
        "sample_every_n_epochs",
        "sample_every_n_steps",
        "sample_sampler",
    ):
        config.pop(key, None)


def _positive_from_dataset(config: dict) -> str:
    train_data_dir = config.get("train_data_dir")
    if not train_data_dir:
        raise AdapterError("随机预览 Prompt 需要填写训练图片目录 train_data_dir")
    sub_dirs = sorted(
        (path for path in glob(os.path.join(train_data_dir, "*")) if os.path.isdir(path)),
        key=lambda path: Path(path).name.lower(),
    )
    if not sub_dirs:
        raise AdapterError("训练数据集路径没有子文件夹，无法随机选取 Prompt")
    prompt_dir = sub_dirs[0]
    txt_files = glob(os.path.join(prompt_dir, "*.txt"))
    if not txt_files:
        raise AdapterError(f"随机预览 Prompt 选择的首个子文件夹没有 txt 文件: {prompt_dir}")
    sample_prompt_file = random.choice(txt_files)
    try:
        return Path(sample_prompt_file).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AdapterError(f"读取预览 Prompt 文件失败: {sample_prompt_file}") from exc


def build_sample_prompt_line(config: dict) -> str:
    positive = config.get("positive_prompts") or DEFAULT_SAMPLE_POSITIVE
    negative = config.get("negative_prompts") or DEFAULT_SAMPLE_NEGATIVE
    if config.get("randomly_choice_prompt"):
        positive = _positive_from_dataset(config)

    width = config.get("sample_width", 1024)
    height = config.get("sample_height", 1024)
    cfg = config.get("sample_cfg", 4.5)
    seed = config.get("sample_seed", 42)
    steps = config.get("sample_steps", 40)
    sampler = str(config.get("sample_sampler") or "euler").strip()

    return build_kohya_sample_prompt_line(
        positive,
        negative,
        width=width,
        height=height,
        cfg=cfg,
        steps=steps,
        seed=seed,
        sampler=sampler,
    )


def _normalize_sample_schedule(config: dict, warnings: list[str]) -> None:
    """Clamp epoch-based sampling so preview can fire before training ends."""
    if not is_empty(config.get("sample_every_n_steps")):
        return

    max_epochs = int_value(config.get("max_train_epochs"), 0)
    if max_epochs <= 0:
        if is_empty(config.get("sample_every_n_epochs")):
            config["sample_every_n_epochs"] = 2
        return

    if is_empty(config.get("sample_every_n_epochs")):
        config["sample_every_n_epochs"] = min(2, max_epochs)
        return

    every_epochs = int_value(config.get("sample_every_n_epochs"), 0)
    if every_epochs <= 0:
        config["sample_every_n_epochs"] = min(2, max_epochs)
        return

    if every_epochs > max_epochs:
        original = every_epochs
        config["sample_every_n_epochs"] = max_epochs
        warnings.append(
            f"sample_every_n_epochs 已从 {original} 调整为 {max_epochs} "
            f"（不超过 max_train_epochs={max_epochs}，否则训练结束前不会生成预览图）"
        )


def apply_anima_fast_preview(config: dict, autosave_dir: str, run_id: str) -> list[str]:
    warnings: list[str] = []
    if not is_preview_enabled(config):
        _strip_preview_fields(config)
        return warnings

    prompt_file = str(config.get("prompt_file") or "").strip()
    if prompt_file:
        path = Path(prompt_file)
        if not path.is_file():
            raise AdapterError(f"Preview prompt file not found: {prompt_file}")
        config["sample_prompts"] = str(path.resolve())
    elif not is_empty(config.get("sample_prompts")):
        path = Path(str(config["sample_prompts"]))
        if not path.is_file():
            raise AdapterError(f"Preview prompt file not found: {path}")
        config["sample_prompts"] = str(path.resolve())
    else:
        autosave = Path(autosave_dir)
        autosave.mkdir(parents=True, exist_ok=True)
        out_path = autosave / f"{run_id}-preview-prompt.txt"
        out_path.write_text(build_sample_prompt_line(config) + "\n", encoding="utf-8")
        config["sample_prompts"] = str(out_path.resolve())

    if config.get("sample_at_first") is None:
        # Default to sampling once at training start so an enabled preview
        # always produces at least one image, even for short/epoch-clamped runs
        # (regression from 7cb49dc, reported in #126). Users can still set it
        # to False explicitly to skip the step-0 sample and lower VRAM peak.
        config["sample_at_first"] = True
    _normalize_sample_schedule(config, warnings)
    config.setdefault("sample_sampler", "euler")

    warnings.append(
        "training preview enabled; sample images will be written under output_dir/sample "
        "(sampling loads VAE/Qwen3 and uses extra VRAM/time)"
    )
    return warnings

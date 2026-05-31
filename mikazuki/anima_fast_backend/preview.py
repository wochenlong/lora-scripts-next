from __future__ import annotations

from glob import glob
from pathlib import Path
import os
import random

from .adapter import AdapterError, is_empty

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
    raw = config.get("enable_preview")
    if raw in (True, "true", "True", "1", 1):
        return True
    if raw in (False, "false", "False", "0", 0):
        return False
    if not is_empty(config.get("prompt_file")):
        return True
    if not is_empty(config.get("positive_prompts")):
        return True
    if not is_empty(config.get("sample_every_n_epochs")) or not is_empty(config.get("sample_every_n_steps")):
        return True
    if config.get("sample_at_first") in (True, "true", "True", "1", 1):
        return True
    return False


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
    sub_dirs = [path for path in glob(os.path.join(train_data_dir, "*")) if os.path.isdir(path)]
    if len(sub_dirs) != 1:
        raise AdapterError("训练数据集下有多个子文件夹，无法启用随机选取 Prompt 功能")
    txt_files = glob(os.path.join(sub_dirs[0], "*.txt"))
    if not txt_files:
        raise AdapterError("训练数据集路径没有 txt 文件")
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

    line = (
        f"{positive} --n {negative} --w {width} --h {height} "
        f"--l {cfg} --s {steps} --d {seed}"
    )
    if sampler:
        line += f" --ss {sampler}"
    return line


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
        config["sample_at_first"] = True
    if is_empty(config.get("sample_every_n_epochs")) and is_empty(config.get("sample_every_n_steps")):
        config["sample_every_n_epochs"] = 2
    config.setdefault("sample_sampler", "euler")

    warnings.append(
        "training preview enabled; sample images will be written under output_dir/sample "
        "(sampling loads VAE/Qwen3 and uses extra VRAM/time)"
    )
    return warnings

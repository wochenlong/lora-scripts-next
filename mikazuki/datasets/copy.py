from __future__ import annotations

import os
import shutil
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from mikazuki.dataset_editor import IMAGE_EXTENSIONS

ALPHA_MODES = {"RGBA", "LA", "PA"}


def flatten_to_white(source: Path, target: Path) -> bool:
    try:
        with Image.open(source) as image:
            has_alpha = image.mode in ALPHA_MODES or (image.mode == "P" and "transparency" in image.info)
            if not has_alpha:
                return False
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[3])
            background.save(target)
        return True
    except (OSError, UnidentifiedImageError):
        return False


def copy_dataset(source: Path, target: Path, flatten_transparent: bool = False) -> dict:
    copied = 0
    flattened = 0
    for dirpath, dirnames, filenames in os.walk(source):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        out_dir = target / Path(dirpath).relative_to(source)
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in filenames:
            src = Path(dirpath) / name
            if src.is_symlink():
                continue
            dst = out_dir / name
            if flatten_transparent and src.suffix.lower() in IMAGE_EXTENSIONS and flatten_to_white(src, dst):
                flattened += 1
            else:
                shutil.copy2(src, dst)
            copied += 1
    return {"copied": copied, "flattened": flattened}

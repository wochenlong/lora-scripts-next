from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from mikazuki.dataset_editor import IMAGE_EXTENSIONS

ALPHA_MODES = {"RGBA", "LA", "PA"}
LAYOUTS = {"preserve", "flatten", "kohya"}
REPEATS_PREFIX = re.compile(r"^\d+_.+")


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


def _sanitize_subset_name(raw: str) -> str:
    cleaned = re.sub(r"[\\/]+", "_", raw).strip("._ ")
    return cleaned or "dataset"


def _base_target_rel(rel: Path, target_name: str, layout: str, repeats: int) -> Path:
    if layout == "preserve":
        return rel
    if layout == "flatten":
        return Path(rel.name)
    parent = rel.parent
    if str(parent) != "." and REPEATS_PREFIX.match(parent.name):
        return rel
    base = target_name if str(parent) == "." else "_".join(parent.parts)
    subset = base if REPEATS_PREFIX.match(base) else f"{repeats}_{_sanitize_subset_name(base)}"
    return Path(subset) / rel.name


def _dedupe(rel: Path, used: set[Path]) -> Path:
    candidate = rel
    index = 2
    while candidate in used:
        candidate = rel.with_name(f"{rel.stem}-{index}{rel.suffix}")
        index += 1
    used.add(candidate)
    return candidate


def copy_dataset(
    source: Path,
    target: Path,
    flatten_transparent: bool = False,
    layout: str = "preserve",
    repeats: int = 10,
) -> dict:
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout: {layout}")
    repeats = max(1, min(int(repeats), 999))

    files: list[tuple[Path, Path]] = []
    for dirpath, dirnames, filenames in os.walk(source):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        for name in filenames:
            src = Path(dirpath) / name
            if src.is_symlink():
                continue
            files.append((src, src.relative_to(source)))
    files.sort(key=lambda item: str(item[1]))

    used: set[Path] = set()
    image_dests: dict[tuple[str, str], Path] = {}
    pending_captions: list[tuple[Path, Path]] = []
    moves: list[tuple[Path, Path]] = []
    deduped = 0

    for src, rel in files:
        is_image = src.suffix.lower() in IMAGE_EXTENSIONS
        if is_image:
            dst_rel = _dedupe(_base_target_rel(rel, target.name, layout, repeats), used)
            image_dests[(str(rel.parent), rel.stem)] = dst_rel
            moves.append((src, dst_rel))
            if dst_rel.name != rel.name:
                deduped += 1
        elif src.suffix.lower() == ".txt":
            pending_captions.append((src, rel))
        else:
            dst_rel = _dedupe(_base_target_rel(rel, target.name, layout, repeats), used)
            moves.append((src, dst_rel))

    for src, rel in pending_captions:
        anchor = image_dests.get((str(rel.parent), rel.stem))
        if anchor is not None:
            dst_rel = _dedupe(anchor.with_suffix(".txt"), used)
        else:
            dst_rel = _dedupe(_base_target_rel(rel, target.name, layout, repeats), used)
        moves.append((src, dst_rel))
        if dst_rel.name != rel.name:
            deduped += 1

    copied = 0
    flattened = 0
    for src, dst_rel in moves:
        dst = target / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if flatten_transparent and src.suffix.lower() in IMAGE_EXTENSIONS and flatten_to_white(src, dst):
            flattened += 1
        else:
            shutil.copy2(src, dst)
        copied += 1
    return {"copied": copied, "flattened": flattened, "deduped": deduped}

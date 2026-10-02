from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from mikazuki.dataset_editor import IMAGE_EXTENSIONS, caption_path_for
from mikazuki.datasets.root import normalize_path, resolve_root

READABILITY_SAMPLE_LIMIT = 20
UNREADABLE_LIST_LIMIT = 10
REPEATS_PREFIX = re.compile(r"^\d+_.+")

KNOWN_ENGINES = {"kohya", "ai-toolkit", "musubi", "diffsynth", "anima-fast"}


def _finding(level: str, code: str, **params) -> dict:
    return {"level": level, "code": code, "params": params}


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        yield path


def _spot_check(images: list[Path]) -> list[str]:
    if len(images) <= READABILITY_SAMPLE_LIMIT:
        sample = images
    else:
        step = len(images) / READABILITY_SAMPLE_LIMIT
        sample = [images[int(i * step)] for i in range(READABILITY_SAMPLE_LIMIT)]
    unreadable: list[str] = []
    for path in sample:
        try:
            with Image.open(path) as image:
                image.verify()
        except (UnidentifiedImageError, OSError):
            unreadable.append(path.name)
    return unreadable


def validate_dataset_path(raw_path: str, engine: str | None = None) -> dict:
    findings: list[dict] = []
    if not raw_path or not raw_path.strip():
        findings.append(_finding("error", "path-empty"))
        return {"path": "", "engine": engine, "exists": False, "stats": None, "findings": findings}

    target = resolve_root(raw_path)
    normalized = normalize_path(target)
    if not target.exists():
        findings.append(_finding("error", "path-missing"))
        return {"path": normalized, "engine": engine, "exists": False, "stats": None, "findings": findings}
    if not target.is_dir():
        findings.append(_finding("error", "not-directory"))
        return {"path": normalized, "engine": engine, "exists": False, "stats": None, "findings": findings}

    images: list[Path] = []
    total_bytes = 0
    for path in _iter_files(target):
        total_bytes += path.stat().st_size
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(path)
    images.sort()

    captioned = sum(1 for image in images if caption_path_for(image).is_file())
    missing = len(images) - captioned
    subdirs = {image.parent for image in images if image.parent != target}

    if not images:
        findings.append(_finding("error", "no-images"))
    else:
        if missing:
            findings.append(_finding("warning", "missing-captions", missing=missing, total=len(images)))
        unreadable = _spot_check(images)
        if unreadable:
            findings.append(_finding(
                "warning", "unreadable-images",
                count=len(unreadable), samples=unreadable[:UNREADABLE_LIST_LIMIT],
            ))
        if subdirs:
            findings.append(_finding("info", "nested-images", dirs=len(subdirs)))

    engine_key = engine if engine in KNOWN_ENGINES else None
    if engine_key == "kohya" and images:
        has_repeats_dir = any(REPEATS_PREFIX.match(path.name) for path in subdirs)
        if not has_repeats_dir:
            findings.append(_finding("info", "kohya-subdir-convention"))

    stats = {
        "image_count": len(images),
        "captioned_count": captioned,
        "missing_caption": missing,
        "subdir_count": len(subdirs),
        "total_bytes": total_bytes,
        "sampled": min(len(images), READABILITY_SAMPLE_LIMIT),
    }
    return {"path": normalized, "engine": engine_key, "exists": True, "stats": stats, "findings": findings}

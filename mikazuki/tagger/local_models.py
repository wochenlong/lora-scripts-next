"""Project-owned local storage for tagger model assets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mikazuki.tagger.interrogators.base import Interrogator


TAGGER_MODELS_DIR_ENV = "MIKAZUKI_TAGGER_MODELS_DIR"
DEFAULT_TAGGER_MODELS_DIR = "tagger-models"
WD14_MODEL_FAMILY = "wd14"
VLM_MODEL_FAMILY = "vlm"


def local_models_root() -> Path:
    configured = os.environ.get(TAGGER_MODELS_DIR_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.cwd() / DEFAULT_TAGGER_MODELS_DIR).resolve()


def local_model_dir(model_key: str) -> Path:
    return local_models_root() / local_model_family(model_key) / model_key


def legacy_local_model_dir(model_key: str) -> Path:
    return local_models_root() / model_key


def local_model_family(model_key: str) -> str:
    if model_key.startswith("wd") or model_key.startswith("cl_tagger"):
        return WD14_MODEL_FAMILY
    return VLM_MODEL_FAMILY


def asset_filenames(interrogator: "Interrogator") -> list[str]:
    files: list[str] = []
    for attr in ("model_path", "tags_path", "tag_mapping_path"):
        value = getattr(interrogator, attr, None)
        if value:
            files.append(str(value).replace("\\", "/"))
    return files


def local_model_asset_paths(
    model_key: str,
    interrogator: "Interrogator",
) -> tuple[Path, ...] | None:
    files = asset_filenames(interrogator)
    if not files:
        return None

    for model_dir in (local_model_dir(model_key), legacy_local_model_dir(model_key)):
        paths = tuple(model_dir / filename for filename in files)
        if all(path.is_file() for path in paths):
            return paths
    return None

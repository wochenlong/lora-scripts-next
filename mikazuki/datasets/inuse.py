from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from mikazuki.datasets.root import get_datasets_root, resolve_root
from mikazuki.tasks import tm
from mikazuki.utils.task_insights import _load_toml, resolve_task_config

ACTIVE_STATUSES = {"CREATED", "RUNNING", "QUEUED"}
DIR_KEYS = ("train_data_dir", "reg_data_dir", "output_data_dir", "dataset_base_path", "source_image_dir")
ARRAY_DIR_KEYS = ("input_data_dirs", "control_data_dirs")


def _iter_dir_values(value) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.splitlines() if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _referenced_dataset_dirs(config: dict):
    ref = str(config.get("dataset_config") or "").strip()
    if not ref:
        return
    try:
        data = _load_toml(resolve_root(ref))
    except Exception:
        return
    for dataset in data.get("datasets") or []:
        if not isinstance(dataset, dict):
            continue
        image_directory = str(dataset.get("image_directory") or "").strip()
        if image_directory:
            yield image_directory
        for subset in dataset.get("subsets") or []:
            if not isinstance(subset, dict):
                continue
            image_dir = str(subset.get("image_dir") or "").strip()
            if image_dir:
                yield image_dir


def _config_dirs(config: dict):
    for key in DIR_KEYS:
        yield from _iter_dir_values(config.get(key))
    for key in ARRAY_DIR_KEYS:
        yield from _iter_dir_values(config.get(key))
    yield from _referenced_dataset_dirs(config)


def datasets_in_use(root: Path | None = None) -> set[str]:
    root = (root or get_datasets_root()).resolve()
    in_use: set[str] = set()
    for task in tm.dump():
        if task["status"] not in ACTIVE_STATUSES:
            continue
        config = resolve_task_config(task["metadata"])
        for raw in _config_dirs(config):
            try:
                rel = resolve_root(raw).relative_to(root)
            except (ValueError, OSError):
                continue
            if rel.parts and not rel.parts[0].startswith("."):
                in_use.add(rel.parts[0])
    return in_use


def ensure_dataset_not_in_use(name: str) -> None:
    if name in datasets_in_use():
        raise HTTPException(status_code=409, detail=f"dataset '{name}' is in use by a running training task")


def ensure_path_not_in_use(raw_path: str) -> None:
    try:
        path = resolve_root(raw_path)
    except (OSError, ValueError):
        return
    try:
        rel = path.relative_to(get_datasets_root())
    except ValueError:
        return
    if rel.parts and not rel.parts[0].startswith("."):
        ensure_dataset_not_in_use(rel.parts[0])

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from mikazuki.datasets.root import get_datasets_root, resolve_root
from mikazuki.tasks import tm
from mikazuki.utils.task_insights import resolve_task_config

ACTIVE_STATUSES = {"CREATED", "RUNNING", "QUEUED"}
DIR_KEYS = ("train_data_dir", "reg_data_dir", "output_data_dir", "dataset_base_path")
ARRAY_DIR_KEYS = ("input_data_dirs",)


def _config_dirs(config: dict):
    for key in DIR_KEYS:
        value = str(config.get(key) or "").strip()
        if value:
            yield value
    for key in ARRAY_DIR_KEYS:
        for item in config.get(key) or []:
            value = str(item).strip()
            if value:
                yield value


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

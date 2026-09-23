import shutil
import uuid
from contextlib import ExitStack
from pathlib import Path

from fastapi import HTTPException

from mikazuki.datasets.locks import dataset_operation
from mikazuki.datasets.sandbox import resolve_dataset_dir
from mikazuki.datasets.stats import cached_overview
from mikazuki.datasets.upload import MIN_FREE_BYTES


def copy_staging_root(datasets_root: Path) -> Path:
    return datasets_root / ".copy-tmp"


def dataset_size(dataset_dir: Path) -> int:
    cached = cached_overview(dataset_dir)
    if cached and cached.get("total_bytes") is not None:
        return cached["total_bytes"]
    return sum(path.stat().st_size for path in dataset_dir.rglob("*") if path.is_file())


def copy_dataset(root: Path, name: str, new_name: str) -> Path:
    source = resolve_dataset_dir(root, name)
    if not source.is_dir():
        raise HTTPException(status_code=404, detail="dataset not found")
    target = resolve_dataset_dir(root, new_name)
    with ExitStack() as stack:
        for lock_name in sorted({source.name, target.name}):
            stack.enter_context(dataset_operation(lock_name))
        if target.exists():
            raise HTTPException(status_code=409, detail="dataset already exists")
        required = dataset_size(source)
        free = shutil.disk_usage(root).free
        if free - required < MIN_FREE_BYTES:
            raise HTTPException(status_code=507, detail="insufficient disk space for copy")
        staging = copy_staging_root(root) / uuid.uuid4().hex
        try:
            shutil.copytree(source, staging)
            staging.rename(target)
        except (OSError, shutil.Error) as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise HTTPException(status_code=500, detail=f"copy failed: {exc}") from exc
    return target

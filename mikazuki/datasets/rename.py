import json
import os
from contextlib import ExitStack
from pathlib import Path

from fastapi import HTTPException

from mikazuki.datasets.locks import dataset_operation
from mikazuki.datasets.sandbox import resolve_dataset_dir
from mikazuki.datasets.trash import trash_root


def _rewrite_trash_manifests(root: Path, old: str, new: str) -> list[tuple[Path, bytes]]:
    backups: list[tuple[Path, bytes]] = []
    trash = trash_root(root)
    if not trash.is_dir():
        return backups
    for batch_dir in trash.iterdir():
        manifest_path = batch_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        raw = manifest_path.read_bytes()
        try:
            manifest = json.loads(raw)
        except ValueError:
            continue
        if manifest.get("dataset") != old:
            continue
        manifest["dataset"] = new
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        backups.append((manifest_path, raw))
    return backups


def rename_dataset(root: Path, name: str, new_name: str) -> Path:
    source = resolve_dataset_dir(root, name)
    if not source.is_dir():
        raise HTTPException(status_code=404, detail="dataset not found")
    target = resolve_dataset_dir(root, new_name)
    if target == source:
        return source
    with ExitStack() as stack:
        for lock_name in sorted({source.name, target.name}):
            stack.enter_context(dataset_operation(lock_name))
        if target.exists():
            raise HTTPException(status_code=409, detail="dataset already exists")
        backups: list[tuple[Path, bytes]] = []
        moved = False
        try:
            os.rename(source, target)
            moved = True
            backups = _rewrite_trash_manifests(root, source.name, target.name)
        except OSError as exc:
            for path, raw in backups:
                path.write_bytes(raw)
            if moved:
                os.rename(target, source)
            raise HTTPException(status_code=500, detail=f"rename failed: {exc}") from exc
    return target

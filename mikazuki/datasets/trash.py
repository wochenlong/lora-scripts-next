from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from mikazuki.dataset_editor import IMAGE_EXTENSIONS
from mikazuki.datasets.locks import dataset_operation
from mikazuki.datasets.sandbox import resolve_dataset_dir

TRASH_DIRNAME = ".trash"


def trash_root(datasets_root: Path) -> Path:
    return datasets_root / TRASH_DIRNAME


def validate_batch_id(batch_id: str) -> str:
    cleaned = (batch_id or "").strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or cleaned.startswith("."):
        raise HTTPException(status_code=400, detail="invalid trash batch id")
    return cleaned


def _resolve_existing(dataset_dir: Path, rel: str) -> Path:
    cleaned = (rel or "").strip().replace("\\", "/")
    if not cleaned:
        raise HTTPException(status_code=400, detail="path is required")
    target = (dataset_dir / cleaned).resolve()
    try:
        target.relative_to(dataset_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes dataset") from exc
    return target


def _linked_paths(dataset_dir: Path, rel: str) -> list[str]:
    target = _resolve_existing(dataset_dir, rel)
    paths = [target]
    if target.suffix.lower() in IMAGE_EXTENSIONS:
        caption = target.with_suffix(".txt")
        if caption.is_file():
            paths.append(caption)
    return paths


def _write_manifest(batch_dir: Path, dataset_name: str, entries: list[str], deleted_at: str, sealed: bool) -> None:
    manifest = {
        "dataset": dataset_name,
        "deleted_at": deleted_at,
        "entries": entries,
        "sealed": sealed,
    }
    (batch_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def soft_delete(datasets_root: Path, dataset_dir: Path, rels: list[str], keep_empty_batch: bool = False) -> dict:
    deleted: list[str] = []
    missing: list[str] = []
    seen: set[Path] = set()
    targets: list[Path] = []
    for rel in rels:
        for path in _linked_paths(dataset_dir, rel):
            if path in seen:
                continue
            seen.add(path)
            if path.is_file():
                targets.append(path)
            else:
                missing.append(str(path.relative_to(dataset_dir)).replace("\\", "/"))
    if not targets and not keep_empty_batch:
        return {"batch": None, "deleted": [], "missing": missing}

    batch_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    batch_dir = trash_root(datasets_root) / batch_id
    planned = [path.relative_to(dataset_dir).as_posix() for path in targets]
    deleted_at = datetime.now(tz=timezone.utc).isoformat()
    batch_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(batch_dir, dataset_dir.name, planned, deleted_at, sealed=False)
    entries: list[str] = []
    for path in targets:
        rel = path.relative_to(dataset_dir).as_posix()
        destination = batch_dir / "files" / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(destination))
        entries.append(rel)
        deleted.append(rel)
    _write_manifest(batch_dir, dataset_dir.name, entries, deleted_at, sealed=True)
    return {"batch": batch_id, "deleted": deleted, "missing": missing}


def _load_manifest(batch_dir: Path) -> dict | None:
    manifest_path = batch_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_trash(datasets_root: Path, dataset_name: str) -> list[dict]:
    root = trash_root(datasets_root)
    if not root.is_dir():
        return []
    batches = []
    for batch_dir in sorted(root.iterdir()):
        if not batch_dir.is_dir():
            continue
        manifest = _load_manifest(batch_dir)
        if not manifest or manifest.get("dataset") != dataset_name:
            continue
        entries = manifest.get("entries", [])
        batches.append(
            {
                "id": batch_dir.name,
                "dataset": manifest.get("dataset"),
                "deleted_at": manifest.get("deleted_at"),
                "count": len(entries),
                "paths": entries,
                "sealed": manifest.get("sealed", True),
            }
        )
    return batches


def list_all_trash(datasets_root: Path) -> list[dict]:
    root = trash_root(datasets_root)
    if not root.is_dir():
        return []
    batches = []
    for batch_dir in sorted(root.iterdir()):
        if not batch_dir.is_dir():
            continue
        manifest = _load_manifest(batch_dir)
        if not manifest:
            continue
        entries = manifest.get("entries", [])
        batches.append(
            {
                "id": batch_dir.name,
                "dataset": manifest.get("dataset"),
                "deleted_at": manifest.get("deleted_at"),
                "count": len(entries),
                "paths": entries,
                "sealed": manifest.get("sealed", True),
            }
        )
    return batches


def _batch_dir(datasets_root: Path, batch_id: str) -> Path:
    batch_dir = trash_root(datasets_root) / validate_batch_id(batch_id)
    if not batch_dir.is_dir() or _load_manifest(batch_dir) is None:
        raise HTTPException(status_code=404, detail="trash batch not found")
    return batch_dir


def _move_no_overwrite(source: Path, target: Path) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except FileExistsError:
        return False
    except OSError:
        try:
            with source.open("rb") as src, target.open("xb") as out:
                shutil.copyfileobj(src, out)
        except FileExistsError:
            return False
        except Exception:
            target.unlink(missing_ok=True)
            raise
    source.unlink()
    return True


def restore_batch(datasets_root: Path, dataset_dir: Path, batch_id: str) -> dict:
    batch_dir = _batch_dir(datasets_root, batch_id)
    manifest = _load_manifest(batch_dir) or {}
    if manifest.get("dataset") != dataset_dir.name:
        raise HTTPException(status_code=404, detail="trash batch not found")
    restored: list[str] = []
    conflicts: list[str] = []
    missing: list[str] = []
    remaining: list[str] = []
    for rel in manifest.get("entries", []):
        source = batch_dir / "files" / rel
        target = _resolve_existing(dataset_dir, rel)
        if not source.is_file():
            missing.append(rel)
            continue
        if target.exists():
            conflicts.append(rel)
            remaining.append(rel)
            continue
        if _move_no_overwrite(source, target):
            restored.append(rel)
        else:
            conflicts.append(rel)
            remaining.append(rel)
    if remaining:
        manifest["entries"] = remaining
        (batch_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        shutil.rmtree(batch_dir, ignore_errors=True)
    return {"restored": restored, "conflicts": conflicts, "missing": missing}


def _ensure_sealed(manifest: dict) -> None:
    if not manifest.get("sealed", True):
        raise HTTPException(
            status_code=409,
            detail="trash batch is from an interrupted deletion; restore it before emptying",
        )


def empty_trash(datasets_root: Path, dataset_name: str, batch_id: str | None = None) -> dict:
    removed = 0
    if batch_id:
        batch_dir = _batch_dir(datasets_root, batch_id)
        manifest = _load_manifest(batch_dir) or {}
        if manifest.get("dataset") != dataset_name:
            raise HTTPException(status_code=404, detail="trash batch not found")
        _ensure_sealed(manifest)
        shutil.rmtree(batch_dir, ignore_errors=True)
        removed = 1
    else:
        for batch in list_trash(datasets_root, dataset_name):
            batch_dir = trash_root(datasets_root) / batch["id"]
            _ensure_sealed(_load_manifest(batch_dir) or {})
            shutil.rmtree(batch_dir, ignore_errors=True)
            removed += 1
    return {"removed": removed}


def soft_delete_dataset(datasets_root: Path, dataset_dir: Path) -> dict:
    batch_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    batch_dir = trash_root(datasets_root) / batch_id
    try:
        batch_dir.mkdir(parents=True)
        os.rename(dataset_dir, batch_dir / "files")
    except OSError:
        shutil.rmtree(batch_dir, ignore_errors=True)
        files = [p for p in sorted(dataset_dir.rglob("*")) if p.is_file()]
        rels = [p.relative_to(dataset_dir).as_posix() for p in files]
        result = soft_delete(datasets_root, dataset_dir, rels, keep_empty_batch=True)
        shutil.rmtree(dataset_dir, ignore_errors=True)
        return result
    files_dir = batch_dir / "files"
    entries = sorted(p.relative_to(files_dir).as_posix() for p in files_dir.rglob("*") if p.is_file())
    _write_manifest(
        batch_dir,
        dataset_dir.name,
        entries,
        datetime.now(tz=timezone.utc).isoformat(),
        sealed=True,
    )
    return {"batch": batch_id, "deleted": entries, "missing": []}


def restore_batch_by_id(datasets_root: Path, batch_id: str) -> dict:
    batch_dir = _batch_dir(datasets_root, batch_id)
    manifest = _load_manifest(batch_dir) or {}
    dataset_name = manifest.get("dataset") or ""
    dataset_dir = resolve_dataset_dir(datasets_root, dataset_name)
    with dataset_operation(dataset_name):
        dataset_dir.mkdir(parents=True, exist_ok=True)
        result = restore_batch(datasets_root, dataset_dir, batch_id)
    result["dataset"] = dataset_name
    return result


def empty_trash_any(datasets_root: Path, batch_id: str | None = None) -> dict:
    removed = 0
    if batch_id:
        batch_dir = _batch_dir(datasets_root, batch_id)
        manifest = _load_manifest(batch_dir) or {}
        dataset_name = manifest.get("dataset") or ""
        with dataset_operation(dataset_name):
            batch_dir = _batch_dir(datasets_root, batch_id)
            _ensure_sealed(_load_manifest(batch_dir) or {})
            shutil.rmtree(batch_dir, ignore_errors=True)
        removed = 1
    else:
        for batch in list_all_trash(datasets_root):
            dataset_name = batch.get("dataset") or ""
            with dataset_operation(dataset_name):
                batch_dir = _batch_dir(datasets_root, batch["id"])
                _ensure_sealed(_load_manifest(batch_dir) or {})
                shutil.rmtree(batch_dir, ignore_errors=True)
                removed += 1
    return {"removed": removed}

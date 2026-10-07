"""Guarded rollback and history cleanup; never calls a model."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from .caption_job import CaptionWriteConflict, caption_path_for, caption_sha256
from .progress import tagger_progress


def _write_bytes(path, content, expected, owner_matches):
    if path.is_symlink() or caption_sha256(path) != expected or not owner_matches():
        raise CaptionWriteConflict("caption changed before rollback")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        if path.is_symlink() or caption_sha256(path) != expected or not owner_matches():
            raise CaptionWriteConflict("caption changed during rollback")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _target(saved, item):
    index = item.get("index")
    paths = saved["recovery"]["paths"]
    if not isinstance(index, int) or not 0 <= index < len(paths):
        raise ValueError("rollback plan missing")
    image = Path(paths[index])
    root = Path(saved["recovery"]["request"]["path"])
    if not image.is_absolute() or not root.is_absolute():
        raise ValueError("rollback plan not absolute")
    image.resolve().relative_to(root.resolve())
    for path in [image, *image.parents]:
        # Windows junctions and POSIX symlinks both invalidate stored targets.
        if path.is_symlink() or (getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("rollback target is a link")
        if path == root:
            break
    return index, caption_path_for(image)


def rollback_job(manager, job_id):
    store = manager.job_store
    saved = store.get(job_id) if store else None
    if not saved:
        raise KeyError("job not found")
    if manager.is_busy() or saved["state"]["phase"] in {"pending", "captioning", "cancelling"}:
        raise RuntimeError("请先结束或取消打标任务")
    from mikazuki.datasets.inuse import ensure_path_not_in_use
    ensure_path_not_in_use(saved["recovery"]["request"]["path"])
    if not tagger_progress.try_begin("captioning", "", "正在回滚 caption"):
        raise RuntimeError("已有打标或下载任务进行中")
    result = {"job_id": job_id, "restored": 0, "conflicts": 0, "skipped": 0, "items": []}
    try:
        for item in saved["state"]["report"]["items"]:
            if item.get("status") != "written":
                continue
            public = {"filename": item["filename"]}
            try:
                index, target = _target(saved, item)
                backup = store.get_backup(job_id, index)
                if not backup or not backup["format_detail"]:
                    raise ValueError("legacy backup has no provenance")
                prior = backup["format_detail"]
                if (backup["content"] is None and backup["before_hash"] is not None) or (
                    backup["content"] is not None and hashlib.sha256(backup["content"]).hexdigest() != backup["before_hash"]
                ):
                    raise ValueError("backup integrity invalid")
                status = store.rollback_status(job_id, index)
                if status == "done":
                    result["skipped"] += 1
                    result["items"].append({**public, "status": "already_restored"})
                    continue
                current = caption_sha256(target)
                record = store.format_record(target)
                pending_write = record and record["writer_job_id"] == job_id and record["after_hash"] == item["after_hash"]
                prior_matches = current == backup["before_hash"] and (
                    current is None or (
                        store.format_owner(target, current) == prior.get("writer_job_id")
                        and (store.find_format_detail(target, current) or {}).get("format") == prior["format"]
                    )
                )
                if status == "prepared" and current == backup["before_hash"] and (prior_matches or pending_write):
                    if backup["content"] is None:
                        store.forget_format(target)
                    elif pending_write:
                        store.remember_format(target, backup["before_hash"], prior["format"], prior.get("tags", []), prior.get("writer_job_id"))
                else:
                    if target.is_symlink() or current != item["after_hash"] or store.format_owner(target, current) != job_id:
                        raise CaptionWriteConflict("caption has another writer")
                    store.mark_rollback(job_id, index, "prepared")
                    if backup["content"] is None:
                        if caption_sha256(target) != current or target.is_symlink() or store.format_owner(target, current) != job_id:
                            raise CaptionWriteConflict("caption changed before removal")
                        target.unlink()
                        store.forget_format(target)
                    else:
                        _write_bytes(target, backup["content"], current, lambda: store.format_owner(target, current) == job_id)
                        store.remember_format(target, backup["before_hash"], prior["format"], prior.get("tags", []), prior.get("writer_job_id"))
                store.mark_rollback(job_id, index, "done")
                result["restored"] += 1
                result["items"].append({**public, "status": "restored", "after_hash": backup["before_hash"]})
            except CaptionWriteConflict:
                result["conflicts"] += 1
                result["items"].append({**public, "status": "conflict", "code": "caption_conflict"})
            except (ValueError, OSError):
                result["skipped"] += 1
                result["items"].append({**public, "status": "unavailable", "code": "caption_rollback_unavailable"})
        return result
    finally:
        tagger_progress._touch(phase="done", message="caption 回滚处理已结束")
        tagger_progress.release()


def delete_history(manager, job_id):
    if manager.is_busy() or tagger_progress.is_busy():
        raise RuntimeError("请先结束或取消打标任务")
    if not manager.job_store or not manager.job_store.get(job_id):
        raise KeyError("job not found")
    if not tagger_progress.try_begin("captioning", "", "正在清理任务记录"):
        raise RuntimeError("已有打标或下载任务进行中")
    try:
        manager.job_store.delete_history(job_id)
        with manager._lock:
            if manager._status["job_id"] == job_id:
                manager._status = manager._idle()
                manager._request = None
                manager._failed = []
        return {"deleted": True, "job_id": job_id}
    finally:
        tagger_progress._touch(phase="done", message="任务历史清理已结束")
        tagger_progress.release()

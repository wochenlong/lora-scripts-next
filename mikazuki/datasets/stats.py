from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from mikazuki.dataset_editor import IMAGE_EXTENSIONS, caption_path_for
from mikazuki.datasets.root import normalize_path
from mikazuki.log import log

OVERVIEW_TTL_SECONDS = 15.0

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dataset-overview")
_lock = threading.Lock()
_entries: dict[str, dict] = {}
_inflight: set[str] = set()


def compute_overview(dataset_dir: Path) -> dict:
    file_count = 0
    captioned_count = 0
    total_bytes = 0
    latest_mtime = 0.0
    for path in dataset_dir.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        total_bytes += stat.st_size
        latest_mtime = max(latest_mtime, stat.st_mtime)
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            file_count += 1
            if caption_path_for(path).is_file():
                captioned_count += 1
    return {
        "state": "ready",
        "file_count": file_count,
        "captioned_count": captioned_count,
        "total_bytes": total_bytes,
        "updated_at": datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat() if latest_mtime else None,
        "computed_at": datetime.now(tz=timezone.utc).isoformat(),
        "error": None,
    }


def _compute_and_store(key: str, dataset_dir: Path) -> None:
    try:
        entry = compute_overview(dataset_dir)
    except Exception as exc:
        log.error(f"Dataset overview failed for {dataset_dir}: {exc}")
        entry = {
            "state": "error",
            "file_count": None,
            "captioned_count": None,
            "total_bytes": None,
            "updated_at": None,
            "computed_at": datetime.now(tz=timezone.utc).isoformat(),
            "error": str(exc),
        }
    with _lock:
        _entries[key] = entry
        _inflight.discard(key)


def _is_fresh(entry: dict) -> bool:
    computed_at = entry.get("computed_at")
    if not computed_at:
        return False
    try:
        computed = datetime.fromisoformat(computed_at).timestamp()
    except ValueError:
        return False
    return time.time() - computed < OVERVIEW_TTL_SECONDS


def get_overview(dataset_dir: Path) -> dict:
    key = normalize_path(dataset_dir)
    with _lock:
        entry = _entries.get(key)
        if entry and _is_fresh(entry):
            return dict(entry)
        if key not in _inflight:
            _inflight.add(key)
            _executor.submit(_compute_and_store, key, dataset_dir)
        if entry:
            stale = dict(entry)
            stale["state"] = "computing"
            return stale
        return {"state": "computing"}


def cached_overview(dataset_dir: Path) -> dict | None:
    key = normalize_path(dataset_dir)
    with _lock:
        entry = _entries.get(key)
        return dict(entry) if entry else None


def invalidate_overview(dataset_dir: Path) -> None:
    key = normalize_path(dataset_dir)
    with _lock:
        _entries.pop(key, None)

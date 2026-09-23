import json
import threading
import time
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 runtime
    import toml as tomllib

from mikazuki.tasks import TaskStatus, tm

ACTIVE_STATUSES = {TaskStatus.CREATED, TaskStatus.QUEUED, TaskStatus.RUNNING}
PATH_KEYS = {"train_data_dir", "reg_data_dir", "image_dir", "source_image_dir", "dataset_base_path"}
LIST_PATH_KEYS = {"control_data_dirs"}

_CACHE_TTL = 1.0
_lock = threading.Lock()
_cache: tuple[float, dict[str, list[dict]]] | None = None


def _collect_strings(node, out: set[str], depth: int = 0):
    if depth > 6:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if key in PATH_KEYS and isinstance(value, str) and value.strip():
                out.add(value)
            elif key in LIST_PATH_KEYS and isinstance(value, list):
                out.update(item for item in value if isinstance(item, str) and item.strip())
            elif isinstance(value, (dict, list)):
                _collect_strings(value, out, depth + 1)
    elif isinstance(node, list):
        for item in node:
            _collect_strings(item, out, depth + 1)


def _load_config_paths(config_path: Path, out: set[str], depth: int = 0):
    try:
        if config_path.suffix.lower() == ".json":
            data = json.loads(config_path.read_text(encoding="utf-8-sig"))
        else:
            with config_path.open("rb") as stream:
                data = tomllib.load(stream)
    except (OSError, ValueError):
        return
    _collect_strings(data, out)
    if depth < 1 and isinstance(data, dict):
        dataset_config = data.get("dataset_config")
        if isinstance(dataset_config, str) and dataset_config.strip():
            nested = _resolve(dataset_config, config_path.parent)
            if nested is not None and nested.is_file() and nested != config_path:
                _load_config_paths(nested, out, depth + 1)


def _resolve(raw: str, cwd: Path) -> Path | None:
    try:
        path = Path(raw.replace("\\", "/")).expanduser()
        return (path if path.is_absolute() else cwd / path).resolve()
    except (OSError, ValueError):
        return None


def _task_dataset_dirs(task) -> list[Path]:
    config_path_raw = task.metadata.get("config_path")
    if not config_path_raw:
        return []
    config_path = Path(config_path_raw)
    if not config_path.is_file():
        return []
    cwd = Path(task.metadata.get("cwd") or task.cwd or config_path.parent)
    raw_paths: set[str] = set()
    _load_config_paths(config_path, raw_paths)
    resolved = []
    for raw in raw_paths:
        path = _resolve(raw, cwd)
        if path is not None:
            resolved.append(path)
    return resolved


def _covers(candidate: Path, dataset_dir: Path) -> bool:
    return candidate == dataset_dir or candidate in dataset_dir.parents or dataset_dir in candidate.parents


def _compute(root: Path) -> dict[str, list[dict]]:
    usage: dict[str, list[dict]] = {}
    dataset_dirs = {p.name: p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")} if root.is_dir() else {}
    if not dataset_dirs:
        return usage
    for task in list(tm.tasks.values()):
        if task.status not in ACTIVE_STATUSES:
            continue
        ref = {"task_id": task.task_id, "job_label": task.metadata.get("job_label") or ""}
        for candidate in _task_dataset_dirs(task):
            for name, dataset_dir in dataset_dirs.items():
                if _covers(candidate, dataset_dir) and ref not in usage.setdefault(name, []):
                    usage[name].append(ref)
    return usage


def in_use_map(root: Path) -> dict[str, list[dict]]:
    global _cache
    with _lock:
        if _cache and time.time() - _cache[0] < _CACHE_TTL:
            return {name: list(refs) for name, refs in _cache[1].items()}
    computed = _compute(root)
    with _lock:
        _cache = (time.time(), computed)
    return {name: list(refs) for name, refs in computed.items()}


def in_use_tasks(root: Path, dataset_name: str) -> list[dict]:
    return in_use_map(root).get(dataset_name, [])


def invalidate_in_use_cache() -> None:
    global _cache
    with _lock:
        _cache = None

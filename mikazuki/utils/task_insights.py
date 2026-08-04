from __future__ import annotations

import re
import time
from pathlib import Path

try:
    import toml

    def _load_toml(path: Path) -> dict:
        return toml.load(path)
except ModuleNotFoundError:  # pragma: no cover - lightweight test environment fallback
    import tomllib

    def _load_toml(path: Path) -> dict:
        return tomllib.loads(path.read_text(encoding="utf-8"))

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
LOSS_TAGS = ("loss/average", "loss/current", "loss/epoch_average", "lr/unet")
LOSS_POINT_LIMIT = 500
SINCE_TOLERANCE_SECONDS = 1.0

_LIST_CACHE_TTL_SECONDS = 2.0
_list_cache: dict[tuple, tuple[float, list[Path]]] = {}
_loss_cache: dict[str, tuple[tuple, dict]] = {}


def resolve_task_config(metadata: dict) -> dict:
    config_path = str((metadata or {}).get("config_path") or "").strip()
    if not config_path:
        return {}
    path = Path(config_path)
    if not path.is_file():
        return {}
    try:
        return _load_toml(path)
    except Exception:
        return {}


def _resolve_dir(value: object) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        return path.resolve()
    except OSError:
        return None


def resolve_task_dirs(metadata: dict) -> dict:
    config = resolve_task_config(metadata)
    dirs = {
        "output_dir": _resolve_dir(config.get("output_dir")),
        "logging_dir": _resolve_dir(config.get("logging_dir") or "./logs"),
        "output_name": str(config.get("output_name") or "").strip(),
    }
    return dirs


def parse_epoch(name: str) -> int | None:
    for pattern in (r"_e(\d{6})_", r"-e(\d+)", r"_e(\d+)", r"epoch[_-]?(\d+)"):
        match = re.search(pattern, name, flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


def _since(metadata: dict) -> float:
    try:
        return float((metadata or {}).get("created_at") or 0) - SINCE_TOLERANCE_SECONDS
    except (TypeError, ValueError):
        return 0.0


def _iter_preview_paths(metadata: dict) -> list[Path]:
    dirs = resolve_task_dirs(metadata)
    output_dir = dirs.get("output_dir")
    if output_dir is None:
        return []
    output_name = dirs.get("output_name") or ""
    since = _since(metadata)
    cache_key = (str(output_dir), output_name, since)
    now = time.monotonic()
    cached = _list_cache.get(cache_key)
    if cached and now - cached[0] < _LIST_CACHE_TTL_SECONDS:
        return cached[1]
    found: dict[str, Path] = {}
    for root in (output_dir / "sample", output_dir):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if output_name and not path.name.startswith(output_name):
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if since and mtime < since:
                continue
            old = found.get(path.name)
            if old is None or mtime >= old.stat().st_mtime:
                found[path.name] = path
    result = sorted(found.values(), key=lambda p: p.stat().st_mtime)
    _list_cache[cache_key] = (now, result)
    return result


def list_preview_images(metadata: dict) -> list[dict]:
    images = []
    for path in _iter_preview_paths(metadata):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        images.append({"name": path.name, "epoch": parse_epoch(path.name), "mtime": mtime})
    return images


def resolve_preview_image(metadata: dict, filename: str) -> Path | None:
    for path in _iter_preview_paths(metadata):
        if path.name == filename:
            return path
    return None


def downsample(points: list[dict], limit: int = LOSS_POINT_LIMIT) -> list[dict]:
    if len(points) <= limit:
        return points
    stride = len(points) / limit
    sampled = [points[int(i * stride)] for i in range(limit)]
    if sampled[-1] is not points[-1]:
        sampled.append(points[-1])
    return sampled


def read_loss_scalars(metadata: dict, limit: int = LOSS_POINT_LIMIT) -> dict:
    dirs = resolve_task_dirs(metadata)
    logging_dir = dirs.get("logging_dir")
    if logging_dir is None or not logging_dir.exists():
        return {}
    output_name = dirs.get("output_name") or ""
    since = _since(metadata)
    try:
        from tensorboard.backend.event_processing import event_accumulator
    except Exception:
        return {}

    run_mtimes: dict[Path, float] = {}
    for event_file in logging_dir.rglob("events.out.tfevents.*"):
        if not event_file.is_file():
            continue
        try:
            mtime = event_file.stat().st_mtime
        except OSError:
            continue
        run_mtimes[event_file.parent] = max(run_mtimes.get(event_file.parent, 0.0), mtime)
    if not run_mtimes:
        return {}

    chosen = _select_run_dir(run_mtimes, output_name, since)
    if chosen is None:
        return {}
    return _read_run_scalars(chosen, limit)


def _run_dir_timestamp(name: str) -> float | None:
    match = re.search(r"(\d{14})", name)
    if not match:
        return None
    try:
        return time.mktime(time.strptime(match.group(1), "%Y%m%d%H%M%S"))
    except ValueError:
        return None


def _select_run_dir(run_mtimes: dict[Path, float], output_name: str, since: float) -> Path | None:
    if since:
        run_mtimes = {path: mtime for path, mtime in run_mtimes.items() if mtime >= since}
        if not run_mtimes:
            return None
    timed = [(path, ts) for path in run_mtimes if (ts := _run_dir_timestamp(path.name)) is not None and ts >= since]
    if timed:
        if since:
            return min(timed, key=lambda item: item[1])[0]
        return max(timed, key=lambda item: item[1])[0]
    named = [path for path in run_mtimes if output_name and output_name in path.name]
    pool = named or list(run_mtimes)
    return max(pool, key=lambda path: run_mtimes[path])


def _read_run_scalars(run_dir: Path, limit: int) -> dict:
    try:
        from tensorboard.backend.event_processing import event_accumulator
    except Exception:
        return {}
    try:
        files = [p for p in run_dir.glob("events.out.tfevents.*") if p.is_file()]
    except OSError:
        return {}
    if not files:
        return {}
    signature = (len(files), sum(p.stat().st_size for p in files), max(p.stat().st_mtime for p in files))
    cached = _loss_cache.get(str(run_dir))
    if cached and cached[0] == signature:
        return dict(cached[1])
    try:
        accumulator = event_accumulator.EventAccumulator(
            str(run_dir),
            size_guidance={event_accumulator.SCALARS: 0},
        )
        accumulator.Reload()
        scalar_tags = set(accumulator.Tags().get("scalars", []))
    except Exception:
        return {}

    series: dict[str, list[dict]] = {}
    for tag in LOSS_TAGS:
        if tag not in scalar_tags:
            continue
        try:
            events = accumulator.Scalars(tag)
        except Exception:
            continue
        points = [{"step": int(event.step), "value": float(event.value)} for event in events]
        if points:
            series[tag] = downsample(points, limit)
    _loss_cache[str(run_dir)] = (signature, series)
    return series

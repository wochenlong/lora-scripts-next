from __future__ import annotations

import io
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
AI_TOOLKIT_BACKEND = "ai-toolkit"
# ai-toolkit's SDTrainer writes a single-key loss_dict plus lr.
AI_TOOLKIT_LOSS_TAGS = ("loss", "lr")
LOSS_POINT_LIMIT = 500
SINCE_TOLERANCE_SECONDS = 1.0
# Finished tasks flush TB events/previews shortly before exiting; keep a small
# upper-bound slack so their own last writes are not cut off.
UNTIL_TOLERANCE_SECONDS = 5.0

_LIST_CACHE_TTL_SECONDS = 2.0
_list_cache: dict[tuple, tuple[float, list[Path]]] = {}
_loss_cache: dict[str, tuple[tuple, dict]] = {}
_thumb_cache: dict[tuple, bytes] = {}
_THUMB_CACHE_LIMIT = 64
THUMB_MAX_SIDE = 384


def preview_thumbnail(path: Path, max_side: int = THUMB_MAX_SIDE) -> bytes | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (str(path), stat.st_mtime, stat.st_size, max_side)
    cached = _thumb_cache.get(key)
    if cached is not None:
        return cached
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(path) as image:
            converted = image.convert("RGB")
            converted.thumbnail((max_side, max_side))
            buffer = io.BytesIO()
            converted.save(buffer, "JPEG", quality=82)
            data = buffer.getvalue()
    except Exception:
        return None
    if len(_thumb_cache) >= _THUMB_CACHE_LIMIT:
        _thumb_cache.clear()
    _thumb_cache[key] = data
    return data


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


def _is_ai_toolkit(metadata: dict) -> bool:
    return str((metadata or {}).get("backend") or "") == AI_TOOLKIT_BACKEND


def resolve_task_dirs(metadata: dict) -> dict:
    # ai-toolkit task configs are YAML (unreadable here); its run handler
    # carries the resolved dirs in metadata instead.
    if _is_ai_toolkit(metadata):
        return {
            "output_dir": _resolve_dir((metadata or {}).get("output_dir")),
            "logging_dir": _resolve_dir((metadata or {}).get("logging_dir")),
            "output_name": str((metadata or {}).get("output_name") or "").strip(),
        }
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


def parse_step(name: str) -> int | None:
    match = re.search(r"_(\d{6})_", name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def parse_ai_toolkit_step(name: str) -> int | None:
    """ai-toolkit sample names: <gen_time_ms>_<step:09d>_<count>.<ext>."""
    match = re.search(r"_(\d{9})_", name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def read_progress(log_lines: list[str]) -> dict:
    fragments: list[str] = []
    for line in log_lines[-400:]:
        fragments.extend(line.replace("\r", "\n").split("\n"))
    progress: dict[str, int] = {}
    for line in reversed(fragments):
        if "total_steps" not in progress:
            match = re.search(r"steps:\s*(\d+)%\|[^|]*\|\s*(\d+)/(\d+)", line)
            if match:
                progress["percent"] = int(match.group(1))
                progress["step"] = int(match.group(2))
                progress["total_steps"] = int(match.group(3))
        if "total_epochs" not in progress:
            match = re.search(r"epoch\s+(\d+)/(\d+)", line)
            if match:
                progress["epoch"] = int(match.group(1))
                progress["total_epochs"] = int(match.group(2))
        if "total_steps" in progress and "total_epochs" in progress:
            break
    return progress


def _since(metadata: dict) -> float:
    # Prefer the actual process start: with the compute queue, created_at is
    # the submission time and may long predate the run, leaking the previous
    # task's late writes into this task's window.
    for key in ("started_at", "created_at"):
        try:
            value = float((metadata or {}).get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value - SINCE_TOLERANCE_SECONDS
    return 0.0


def _until(metadata: dict) -> float | None:
    """Upper bound for finished tasks: files written after finished_at belong
    to later tasks sharing the same output/logging dirs."""
    try:
        finished = float((metadata or {}).get("finished_at") or 0)
    except (TypeError, ValueError):
        return None
    return finished + UNTIL_TOLERANCE_SECONDS if finished > 0 else None


def _iter_preview_paths(metadata: dict) -> list[Path]:
    dirs = resolve_task_dirs(metadata)
    output_dir = dirs.get("output_dir")
    if output_dir is None:
        return []
    output_name = dirs.get("output_name") or ""
    since = _since(metadata)
    until = _until(metadata)
    ai_toolkit = _is_ai_toolkit(metadata)
    # ai-toolkit samples land in <training_folder>/<name>/samples/ and their
    # filenames start with a gen-time millisecond timestamp, not output_name.
    if ai_toolkit:
        roots = [output_dir / output_name / "samples"] if output_name else [output_dir]
    else:
        roots = [output_dir / "sample", output_dir]
    cache_key = (str(output_dir), output_name, since, until, ai_toolkit)
    now = time.monotonic()
    cached = _list_cache.get(cache_key)
    if cached and now - cached[0] < _LIST_CACHE_TTL_SECONDS:
        return cached[1]
    found: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if not ai_toolkit and output_name and not path.name.startswith(output_name):
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if since and mtime < since:
                continue
            if until and mtime > until:
                continue
            old = found.get(path.name)
            if old is None or mtime >= old.stat().st_mtime:
                found[path.name] = path
    result = sorted(found.values(), key=lambda p: p.stat().st_mtime)
    _list_cache[cache_key] = (now, result)
    return result


def list_preview_images(metadata: dict) -> list[dict]:
    ai_toolkit = _is_ai_toolkit(metadata)
    images = []
    for path in _iter_preview_paths(metadata):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        step = parse_ai_toolkit_step(path.name) if ai_toolkit else parse_step(path.name)
        images.append({"name": path.name, "epoch": parse_epoch(path.name), "step": step, "mtime": mtime})
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
    until = _until(metadata)
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

    chosen = _select_run_dir(run_mtimes, output_name, since, until)
    if chosen is None:
        return {}
    tags = AI_TOOLKIT_LOSS_TAGS if _is_ai_toolkit(metadata) else LOSS_TAGS
    return _read_run_scalars(chosen, limit, tags)


def _run_dir_timestamp(name: str) -> float | None:
    match = re.search(r"(\d{14})", name)
    if not match:
        return None
    try:
        return time.mktime(time.strptime(match.group(1), "%Y%m%d%H%M%S"))
    except ValueError:
        return None


def _select_run_dir(run_mtimes: dict[Path, float], output_name: str, since: float, until: float | None = None) -> Path | None:
    if since:
        run_mtimes = {path: mtime for path, mtime in run_mtimes.items() if mtime >= since}
    if until:
        run_mtimes = {path: mtime for path, mtime in run_mtimes.items() if mtime <= until}
    if not run_mtimes:
        return None
    timed = [
        (path, ts)
        for path in run_mtimes
        if (ts := _run_dir_timestamp(path.name)) is not None and ts >= since and (until is None or ts <= until)
    ]
    if timed:
        if since:
            return min(timed, key=lambda item: item[1])[0]
        return max(timed, key=lambda item: item[1])[0]
    named = [path for path in run_mtimes if output_name and output_name in path.name]
    pool = named or list(run_mtimes)
    return max(pool, key=lambda path: run_mtimes[path])


def _read_run_scalars(run_dir: Path, limit: int, tags=LOSS_TAGS) -> dict:
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
        return dict(cached[1]) if cached else {}

    series: dict[str, list[dict]] = {}
    for tag in tags:
        if tag not in scalar_tags:
            continue
        try:
            events = accumulator.Scalars(tag)
        except Exception:
            continue
        points = [{"step": int(event.step), "value": float(event.value)} for event in events]
        if points:
            series[tag] = downsample(points, limit)
    if not series and cached:
        return dict(cached[1])
    _loss_cache[str(run_dir)] = (signature, series)
    return series

#!/usr/bin/env python3
"""Training monitor HTTP server.

Provides:
  GET /               → serves index.html
  GET /static/*.css   → CSS
  GET /static/*.js    → JS
  GET /api/status     → JSON training status
  GET /preview-image  → preview images (sandboxed)
  GET /favicon.ico    → favicon
  GET /assets/*       → static assets
"""
from __future__ import annotations

import json
import math
import mimetypes
import os
import re
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from mikazuki.anima_fast_backend.progress import (
    merge_anima_training_metrics,
    metrics_from_anima_events,
    read_jsonl_events,
)


HOST = os.environ.get("TRAIN_MONITOR_HOST", "127.0.0.1")
PORT = int(os.environ.get("TRAIN_MONITOR_PORT", 6008))
_GUI_API_PORT = int(os.environ.get("MIKAZUKI_PORT", 28000))
GUI_API = f"http://127.0.0.1:{_GUI_API_PORT}/api"
STATIC_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = REPO / "output"
LOG_DIR = REPO / "logs"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
PROGRESS_STALL_SECONDS = 120
GPU_IDLE_MEMORY_MB = 512
TASK_PROGRESS_STATE: dict[str, dict[str, float | int]] = {}
TENSORBOARD_SCALAR_TAGS = ("loss/average", "loss/current", "loss/epoch_average", "lr/unet")
TENSORBOARD_LOSS_LIMIT = 10000

STRONG_ERROR_PATTERNS = [
    r"\btraceback\b",
    r"\b(?:runtimeerror|typeerror|valueerror|modulenotfounderror|importerror|oserror):",
    r"cuda out of memory",
    r"no such file or directory",
    r"error executing job",
    r"process .*exited with non[- ]zero",
    r"exit(?:ed)? with code [1-9]\d*",
    r"failed to (?:load|initialize|open|import|download|start|create)",
]
WARNING_PATTERNS = [
    r"\bwarning\b",
    r"no regularization images",
    r"missing source model",
    r"unexpected missing keys",
]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def fetch_json(url: str, timeout: float = 2.5) -> dict:
    with urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def gui_api_candidates() -> list[str]:
    ports: list[int] = []
    for value in (os.environ.get("MIKAZUKI_PORT"), "28000"):
        try:
            port = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if port not in ports:
            ports.append(port)
    return [f"http://127.0.0.1:{port}/api" for port in ports]


def fetch_gui_json(path: str, timeout: float = 2.5) -> tuple[dict, str]:
    errors: list[str] = []
    for api_base in gui_api_candidates():
        try:
            return fetch_json(f"{api_base}{path}", timeout=timeout), api_base
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            errors.append(f"{api_base}: {exc}")
            continue
    raise OSError("; ".join(errors) or "no GUI API candidates")


def api_data(payload: dict) -> dict:
    return payload.get("data") or {}


def human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def first_matching_line(lines: list[str], patterns: list[str]) -> str:
    for line in reversed(lines):
        for pattern in patterns:
            if re.search(pattern, line, flags=re.IGNORECASE):
                return line.strip()
    return ""


def format_duration(value: str) -> str:
    parts = [int(part) for part in value.split(":") if part.isdigit()]
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours, minutes, seconds = 0, parts[0], parts[1]
    else:
        return value

    if hours:
        return f"{hours}小时{minutes:02d}分{seconds:02d}秒"
    if minutes:
        return f"{minutes}分{seconds:02d}秒"
    return f"{seconds}秒"


def resolve_repo_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = REPO / path
    try:
        return path.resolve()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# File scanning
# ---------------------------------------------------------------------------

MODEL_FILE_GLOBS = ("*.safetensors", "*.ckpt", "*.pt")


def _parse_epoch_from_name(name: str) -> int | None:
    for pattern in (
        r"-e(\d+)",
        r"_e(\d+)",
        r"epoch[_-]?(\d+)",
        r"e(\d+)\.",
        r"model-e(\d+)",
    ):
        match = re.search(pattern, name, flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


def _model_file_entry(path: Path) -> dict:
    st = path.stat()
    try:
        rel_path = str(path.relative_to(REPO)).replace("\\", "/")
    except ValueError:
        rel_path = str(path)
    try:
        folder = str(path.parent.relative_to(REPO)).replace("\\", "/")
    except ValueError:
        folder = str(path.parent)
    return {
        "name": path.name,
        "path": str(path),
        "size": human_size(st.st_size),
        "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "mtime_ts": st.st_mtime,
        "rel_path": rel_path,
        "folder": folder,
        "ext": path.suffix.lower(),
        "epoch": _parse_epoch_from_name(path.name),
    }


def newest_model_files(root: Path, limit: int = 12) -> list[dict]:
    if not root.exists():
        return []
    files: list[Path] = []
    for pattern in MODEL_FILE_GLOBS:
        files.extend(root.rglob(pattern))
    files = [p for p in files if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [_model_file_entry(p) for p in files[:limit]]


def newest_files(root: Path, limit: int = 8) -> list[dict]:
    if not root.exists():
        return []
    patterns = ("*.safetensors", "*.ckpt", "*.pt", "*.toml", "*.json")
    files: list[Path] = []
    for pattern in patterns:
        files.extend(root.rglob(pattern))
    files = [p for p in files if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files[:limit]:
        st = p.stat()
        out.append({
            "name": p.name,
            "path": str(p),
            "size": human_size(st.st_size),
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "mtime_ts": st.st_mtime,
        })
    return out


def build_model_outputs(train_out: Path | None) -> dict:
    scope_label = ""
    if train_out is not None:
        try:
            scope_label = str(train_out.relative_to(REPO)).replace("\\", "/")
        except ValueError:
            scope_label = str(train_out)

    primary: list[dict] = []
    if train_out is not None and train_out.exists():
        primary = newest_model_files(train_out, limit=12)

    primary_paths = {item["path"] for item in primary}
    other: list[dict] = []
    if OUTPUT_DIR.exists():
        for item in newest_model_files(OUTPUT_DIR, limit=24):
            if item["path"] in primary_paths:
                continue
            other.append(item)
            if len(other) >= 8:
                break

    combined = primary if primary else newest_model_files(OUTPUT_DIR, limit=8)
    return {
        "output_scope": scope_label,
        "outputs_primary": primary,
        "outputs_other": other,
        "outputs": combined,
    }


def newest_preview_images(
    limit: int = 6,
    output_dir: Path | None = None,
    output_name: str = "",
    max_epochs: int = 0,
) -> list[dict]:
    config = latest_training_config()
    if output_dir is None:
        output_dir = resolve_repo_path(str(config.get("output_dir", "")))
    if not output_name:
        output_name = str(config.get("output_name", "")).strip()
    if max_epochs <= 0:
        try:
            max_epochs = int(float(str(config.get("max_train_epochs", "")).strip()))
        except ValueError:
            max_epochs = 0

    def _collect(name_filter: str) -> dict[str, Path]:
        newest_by_name: dict[str, Path] = {}
        roots: list[Path] = []
        if output_dir is not None:
            roots.extend([output_dir / "sample", output_dir])
        else:
            roots.extend([OUTPUT_DIR / "sample", OUTPUT_DIR, LOG_DIR])
        for root in roots:
            if not root.exists():
                continue
            for p in root.rglob("*"):
                if not p.is_file() or p.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                if name_filter and not p.name.startswith(name_filter):
                    continue
                old = newest_by_name.get(p.name)
                if old is None or p.stat().st_mtime >= old.stat().st_mtime:
                    newest_by_name[p.name] = p
        return newest_by_name

    newest_by_name = _collect(output_name)
    if not newest_by_name and output_name:
        newest_by_name = _collect("")

    all_files = list(newest_by_name.values())
    all_files.sort(key=lambda p: p.stat().st_mtime)
    selected: list[Path] = []
    if all_files:
        selected.append(all_files[0])
    recent_files = all_files[-(limit - 1):] if limit > 1 else []
    for p in recent_files:
        if p not in selected:
            selected.append(p)
        if len(selected) >= limit:
            break

    unique_files = selected
    out = []
    for index, p in enumerate(unique_files):
        st = p.stat()
        try:
            url_path = str(p.relative_to(REPO))
        except ValueError:
            url_path = str(p.resolve())
        epoch_match = re.search(r"_e(?P<epoch>\d{6})_", p.name)
        epoch = int(epoch_match.group("epoch")) if epoch_match else None
        role = ""
        if index == 0 and len(unique_files) > 1:
            role = "基线图"
        elif index == len(unique_files) - 1:
            role = "最新图"
        out.append({
            "name": p.name,
            "path": str(p),
            "size": human_size(st.st_size),
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "url": f"/preview-image?path={quote(url_path)}",
            "role": role,
            "epoch": epoch,
            "max_epoch": max_epochs,
        })
    return out


# ---------------------------------------------------------------------------
# TensorBoard scalar reading
# ---------------------------------------------------------------------------

def tensorboard_loss_scalars(limit: int = TENSORBOARD_LOSS_LIMIT) -> list[dict]:
    """Read real TensorBoard scalar curves from the latest event run."""
    try:
        from tensorboard.backend.event_processing import event_accumulator
    except Exception:
        return []

    if not LOG_DIR.exists():
        return []

    event_files = [p for p in LOG_DIR.rglob("events.out.tfevents.*") if p.is_file()]
    if not event_files:
        return []

    run_dirs: dict[Path, float] = {}
    for event_file in event_files:
        try:
            run_dirs[event_file.parent] = max(
                run_dirs.get(event_file.parent, 0.0),
                event_file.stat().st_mtime,
            )
        except OSError:
            continue

    for run_dir, _ in sorted(run_dirs.items(), key=lambda item: item[1], reverse=True):
        try:
            accumulator = event_accumulator.EventAccumulator(
                str(run_dir),
                size_guidance={event_accumulator.SCALARS: 0},
            )
            accumulator.Reload()
            scalar_tags = set(accumulator.Tags().get("scalars", []))
        except Exception:
            continue

        series = []
        for tag in TENSORBOARD_SCALAR_TAGS:
            if tag not in scalar_tags:
                continue
            try:
                events = accumulator.Scalars(tag)[-limit:]
            except Exception:
                continue
            points = [
                {
                    "step": int(event.step),
                    "value": float(event.value),
                }
                for event in events
            ]
            if not points:
                continue
            values = [point["value"] for point in points]
            series.append({
                "tag": tag,
                "name": tag.split("/", 1)[-1].replace("_", " "),
                "points": points,
                "latest": values[-1],
                "min": min(values),
                "max": max(values),
                "run": str(run_dir.relative_to(REPO)) if run_dir.is_relative_to(REPO) else str(run_dir),
            })
        if series:
            return series

    return []


# ---------------------------------------------------------------------------
# Training config parsing
# ---------------------------------------------------------------------------

_TOML_STR_KEYS = ("output_dir", "output_name", "optimizer_type", "lr_scheduler",
                   "network_module", "network_args", "train_data_dir", "source_image_dir", "reg_data_dir",
                   "resolution", "mixed_precision")
_TOML_NUM_KEYS = ("max_train_epochs", "max_train_steps", "learning_rate", "unet_lr",
                   "text_encoder_lr", "network_dim", "network_alpha", "train_batch_size",
                   "gradient_accumulation_steps", "save_every_n_epochs", "save_every_n_steps",
                   "noise_offset", "clip_skip", "seed", "lr_warmup_steps")
_TOML_BOOL_KEYS = ("gradient_checkpointing", "full_bf16", "full_fp16")


def latest_training_config() -> dict:
    autosave_dir = REPO / "config/autosave"
    if not autosave_dir.exists():
        return {}
    configs = sorted(autosave_dir.glob("*.toml"), key=lambda p: p.stat().st_mtime, reverse=True)
    for config_path in configs:
        try:
            text = config_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        config = {}
        for key in _TOML_STR_KEYS:
            match = re.search(rf'^{key}\s*=\s*["\'](?P<value>.*?)["\']\s*$', text, flags=re.MULTILINE)
            if match:
                config[key] = match.group("value")
        for key in _TOML_NUM_KEYS:
            match = re.search(rf'^{key}\s*=\s*(?P<value>[0-9.eE+-]+)\s*$', text, flags=re.MULTILINE)
            if match:
                config[key] = match.group("value")
        for key in _TOML_BOOL_KEYS:
            match = re.search(rf'^{key}\s*=\s*(?P<value>true|false)\s*$', text, flags=re.MULTILINE | re.IGNORECASE)
            if match:
                config[key] = match.group("value").lower()
        output_dir = config.get("output_dir")
        if output_dir:
            config["_config_path"] = str(config_path)
            return config
    return {}


def _count_dataset_images(train_data_dir: str, reg_data_dir: str | None) -> dict:
    """Scan kohya-style dataset dir to count images and repeats."""
    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif", ".avif"}
    result: dict = {}

    def _scan(base_dir: str) -> tuple[int, int]:
        """Return (total images with repeats, raw image count)."""
        base = Path(base_dir)
        if not base.exists():
            return 0, 0
        total_with_repeats = 0
        raw_count = 0
        subdirs = [d for d in base.iterdir() if d.is_dir()]
        if subdirs:
            for d in subdirs:
                match = re.match(r"^(\d+)_", d.name)
                repeats = int(match.group(1)) if match else 1
                imgs = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
                raw_count += len(imgs)
                total_with_repeats += repeats * len(imgs)
        else:
            imgs = [f for f in base.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
            raw_count = len(imgs)
            total_with_repeats = raw_count
        return total_with_repeats, raw_count

    train_total, train_raw = _scan(train_data_dir)
    result["train_images"] = train_raw
    result["train_images_repeated"] = train_total

    reg_total = 0
    if reg_data_dir:
        reg_total_raw, reg_raw = _scan(reg_data_dir)
        if reg_raw > 0:
            reg_matched = max(reg_total_raw, train_total)
            result["reg_images"] = reg_raw
            result["reg_images_matched"] = reg_matched
            reg_total = reg_matched

    result["samples_per_epoch"] = train_total + reg_total
    return result


def _extract_train_params(config: dict) -> list[dict]:
    """Build ordered list of key training hyperparameters for the monitor UI."""
    if not config:
        return []
    params = []

    def _add(label: str, key: str, fmt: str = ""):
        val = config.get(key)
        if val is None or val == "":
            return
        if fmt == "lr":
            try:
                n = float(val)
                val = f"{n:.2e}" if n < 0.001 else str(n)
            except ValueError:
                pass
        params.append({"label": label, "value": str(val)})

    train_data_dir = config.get("train_data_dir") or config.get("source_image_dir") or ""
    if train_data_dir:
        resolved = resolve_repo_path(train_data_dir)
        reg_dir = config.get("reg_data_dir", "")
        resolved_reg = resolve_repo_path(reg_dir) if reg_dir else None
        ds = _count_dataset_images(str(resolved) if resolved else train_data_dir,
                                   str(resolved_reg) if resolved_reg else None)
        train_img = ds.get("train_images", 0)
        train_repeated = ds.get("train_images_repeated", 0)
        samples = ds.get("samples_per_epoch", 0)

        bs = max(1, int(float(config.get("train_batch_size", "1"))))
        ga = max(1, int(float(config.get("gradient_accumulation_steps", "1"))))
        effective_bs = bs * ga

        if samples > 0:
            batches_per_epoch = math.ceil(samples / bs)
            steps_per_epoch = math.ceil(batches_per_epoch / ga)

            epochs_str = config.get("max_train_epochs", "")
            steps_str = config.get("max_train_steps", "")

            detail_parts = [f"{train_img}图 × {train_repeated // train_img if train_img else 1}r"]
            if ds.get("reg_images"):
                detail_parts.append(f"+{ds['reg_images']}正则")
            detail_parts.append(f"÷ BS{effective_bs}")
            detail = " ".join(detail_parts)

            if epochs_str:
                epochs = int(float(epochs_str))
                total_steps = epochs * steps_per_epoch
                params.append({"label": "总步数", "value": f"{total_steps}（{detail} × {epochs}ep）"})
            elif steps_str:
                total_steps = int(float(steps_str))
                params.append({"label": "总步数", "value": f"{total_steps}（手动设定）"})
            else:
                params.append({"label": "每 Epoch", "value": f"{steps_per_epoch} 步（{detail}）"})

    _add("学习率", "learning_rate", "lr")
    _add("UNet LR", "unet_lr", "lr")
    _add("TE LR", "text_encoder_lr", "lr")
    _add("优化器", "optimizer_type")
    _add("调度器", "lr_scheduler")
    _add("Rank (dim)", "network_dim")
    _add("Alpha", "network_alpha")
    _add("总 Epochs", "max_train_epochs")
    _add("分辨率", "resolution")

    warmup = config.get("lr_warmup_steps", "")
    if warmup and warmup not in ("0", "0.0"):
        params.append({"label": "Warmup", "value": f"{warmup} 步"})

    save_ep = config.get("save_every_n_epochs")
    save_st = config.get("save_every_n_steps")
    if save_ep and save_ep != "0":
        params.append({"label": "保存频率", "value": f"每 {save_ep} epoch"})
    elif save_st and save_st != "0":
        params.append({"label": "保存频率", "value": f"每 {save_st} 步"})

    if config.get("full_bf16") == "true":
        params.append({"label": "精度", "value": "BF16"})
    elif config.get("full_fp16") == "true":
        params.append({"label": "精度", "value": "FP16"})
    else:
        mp = config.get("mixed_precision", "")
        if mp:
            params.append({"label": "精度", "value": mp.upper()})

    noise = config.get("noise_offset", "")
    if noise and noise not in ("0", "0.0", "0.00"):
        params.append({"label": "Noise Offset", "value": noise})
    _add("Clip Skip", "clip_skip")
    _add("Seed", "seed")

    return params


# ---------------------------------------------------------------------------
# GPU monitoring (pynvml)
# ---------------------------------------------------------------------------

_nvml_initialized = False


def _ensure_nvml() -> bool:
    global _nvml_initialized
    if _nvml_initialized:
        return True
    try:
        import pynvml
        pynvml.nvmlInit()
        _nvml_initialized = True
        return True
    except Exception:
        return False


def gpu_info() -> dict | None:
    """Collect GPU metrics via pynvml. Returns info for the first GPU."""
    if not _ensure_nvml():
        return None
    try:
        import pynvml
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        try:
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        except Exception:
            temp = None
        try:
            power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
            power_w = round(power_mw / 1000, 1)
        except Exception:
            power_w = None
        try:
            power_limit_mw = pynvml.nvmlDeviceGetEnforcedPowerLimit(handle)
            power_limit_w = round(power_limit_mw / 1000, 1)
        except Exception:
            power_limit_w = None
        return {
            "name": name,
            "vram_used_mb": round(mem.used / (1024 * 1024)),
            "vram_total_mb": round(mem.total / (1024 * 1024)),
            "gpu_load": util.gpu,
            "mem_load": util.memory,
            "temperature": temp,
            "power_w": power_w,
            "power_limit_w": power_limit_w,
        }
    except Exception:
        return None


def gpu_memory_used_mb() -> int | None:
    info = gpu_info()
    return info["vram_used_mb"] if info else None


# ---------------------------------------------------------------------------
# Progress health tracking
# ---------------------------------------------------------------------------

def update_progress_health(task_id: str, task_status: str, metrics: dict) -> None:
    if task_status != "RUNNING":
        TASK_PROGRESS_STATE.pop(task_id, None)
        return

    step = metrics.get("step")
    if not isinstance(step, int):
        return

    now = time.time()
    state = TASK_PROGRESS_STATE.get(task_id)
    if state is None or state.get("step") != step:
        TASK_PROGRESS_STATE[task_id] = {"step": step, "changed_at": now}
        metrics["progress_stalled"] = False
        metrics["progress_stalled_seconds"] = 0
        return

    stalled_seconds = max(0, int(now - float(state.get("changed_at", now))))
    sampling = metrics.get("sampling") if isinstance(metrics.get("sampling"), dict) else {}
    metrics["progress_stalled_seconds"] = stalled_seconds
    metrics["progress_stalled"] = stalled_seconds >= PROGRESS_STALL_SECONDS and not sampling.get("active")


# ---------------------------------------------------------------------------
# Model type inference
# ---------------------------------------------------------------------------

def _infer_adapter_type(source: str) -> str:
    if "enable tlora" in source or "tlora_anima" in source or '"tlora"' in source or "lora_type = \"tlora\"" in source:
        return "T-LoRA"
    if "lokrmodule" in source or "algo=lokr" in source or "algo = lokr" in source or '"lokr"' in source or "lora_type = \"lokr\"" in source:
        return "LoKr"
    if "lohamodule" in source or "networks.loha" in source:
        return "LoHa"
    if "lora_type = \"lora_fa\"" in source or '"lora_fa"' in source:
        return "LoRA-FA"
    if "lora_type = \"vera\"" in source or '"vera"' in source:
        return "VeRA"
    if "lycoris.kohya" in source:
        return "LyCORIS"
    return "LoRA"


def infer_model_type(lines: list[str]) -> str:
    text = "\n".join(lines[-1000:]).lower()
    config_text = ""
    autosaves = sorted((REPO / "config/autosave").glob("*.toml"), key=lambda p: p.stat().st_mtime, reverse=True)
    if autosaves:
        try:
            config_text = autosaves[0].read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            config_text = ""
    source = text + "\n" + config_text
    adapter = _infer_adapter_type(source)
    anima_network = "anima_train_network" in source
    anima_finetune = not anima_network and (
        "anima-finetune" in source
        or "anima_train.py" in source
        or "scripts/dev/anima_train" in source
        or "scripts\\dev\\anima_train" in source
    )
    if anima_finetune:
        return "Anima Finetune"
    if (
        anima_network
        or "lora_anima" in source
        or "tlora_anima" in source
        or "qwen3" in source
    ):
        return f"Anima {adapter}"
    if "flux_train_network" in source or "flux-lora" in source or "t5xxl" in source:
        return f"Flux {adapter}"
    if "sdxl_train_network" in source or "sdxl-lora" in source or "v_prediction" in source:
        return f"SDXL {adapter}"
    if "train_network.py" in source:
        return adapter
    return "未知类型"


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

def parse_log(lines: list[str]) -> dict:
    text = "\n".join(lines[-5000:])
    joined = "\r".join(lines[-5000:])
    source = joined if "|" in joined else text
    info: dict[str, object] = {}

    progress_matches = list(re.finditer(
        r"(?:^|[\r\n])steps:\s*(?P<pct>\d{1,3})%\|.*?\|\s*(?P<step>\d+)\s*/\s*(?P<total>\d+)"
        r"(?:\s*\[(?P<elapsed>[^<,\]]+)(?:<(?P<eta>[^,\]]+))?[^\]]*\])?",
        source,
    ))
    if progress_matches:
        m = progress_matches[-1]
        step = int(m.group("step"))
        total = int(m.group("total"))
        elapsed = m.group("elapsed") or ""
        eta = (m.group("eta") or "").strip()
        if eta in ("?", "-"):
            eta = ""
        info.update({
            "percent": min(100.0, round(step * 100 / total, 2)) if total else int(m.group("pct")),
            "step": step,
            "total_steps": total,
            "eta": eta,
        })
        if elapsed:
            duration = format_duration(elapsed)
            info["elapsed"] = duration
            if total and step >= total:
                info["duration"] = duration

    sample_matches = list(re.finditer(
        r"Sampling:\s*(?P<pct>\d{1,3})%\|.*?\|\s*(?P<step>\d+)\s*/\s*(?P<total>\d+)"
        r"(?:\s*\[(?P<elapsed>[^<,\]]+)(?:<(?P<eta>[^,\]]+))?[^\]]*\])?",
        source,
    ))
    sample_context = re.findall(r"Generating sample images\s+.*?at step\s+(\d+)", text, flags=re.S)
    if sample_matches:
        sm = sample_matches[-1]
        sample_step = int(sm.group("step"))
        sample_total = int(sm.group("total"))
        sample_percent = min(100.0, round(sample_step * 100 / sample_total, 2)) if sample_total else int(sm.group("pct"))
        info["sampling"] = {
            "active": sample_percent < 100,
            "percent": sample_percent,
            "step": sample_step,
            "total_steps": sample_total,
            "eta": sm.group("eta") or "",
            "train_step": sample_context[-1] if sample_context else "",
        }
    elif sample_context:
        info["sampling"] = {
            "active": False,
            "percent": 100,
            "step": 0,
            "total_steps": 0,
            "eta": "",
            "train_step": sample_context[-1],
        }

    epoch_matches = re.findall(r"(?:epoch|Epoch)\s*[:= ]\s*(\d+)(?:\s*/\s*(\d+))?", text)
    if epoch_matches:
        current, total = epoch_matches[-1]
        info["epoch"] = current + (f"/{total}" if total else "")

    loss_matches = re.findall(
        r"(?:loss|train_loss|avr_loss|loss/average|loss/current)\s*[=:]\s*([0-9.eE+-]+)",
        source,
    )
    if loss_matches:
        info["loss"] = loss_matches[-1]

    loss_points: list[dict[str, float | int]] = []
    for m in re.finditer(
        r"(?:^|[\r\n])steps:.*?\|\s*(?P<step>\d+)\s*/\s*(?P<total>\d+)"
        r".*?(?:avr_loss|train_loss|loss/average|loss/current|loss)\s*[=:]\s*(?P<loss>[0-9.eE+-]+)",
        source,
    ):
        try:
            loss_points.append({"step": int(m.group("step")), "loss": float(m.group("loss"))})
        except ValueError:
            continue
    if loss_points:
        deduped: dict[int, float] = {}
        for point in loss_points:
            deduped[int(point["step"])] = float(point["loss"])
        compact = [{"step": step, "loss": loss} for step, loss in sorted(deduped.items())]
        smoothed = []
        ema = compact[0]["loss"]
        alpha = 0.08
        for point in compact:
            ema = alpha * point["loss"] + (1 - alpha) * ema
            smoothed.append({"step": point["step"], "loss": round(ema, 6)})

        chart_points = smoothed[-240:]
        if len(chart_points) > 120:
            stride = max(1, len(chart_points) // 120)
            chart_points = chart_points[::stride]
            if chart_points[-1]["step"] != smoothed[-1]["step"]:
                chart_points.append(smoothed[-1])

        info["loss_points"] = chart_points
        baseline_loss = compact[0]["loss"]
        current_loss = compact[-1]["loss"]
        if baseline_loss > 0:
            loss_drop_percent = (baseline_loss - current_loss) * 100 / baseline_loss
            info["loss_baseline"] = round(baseline_loss, 6)
            info["loss_current"] = round(current_loss, 6)
            info["loss_drop_percent"] = round(loss_drop_percent, 2)
            info["relative_loss_points"] = [
                {
                    "step": point["step"],
                    "relative": round(point["loss"] * 100 / baseline_loss, 3),
                }
                for point in chart_points
            ]
        if len(compact) >= 8:
            window = max(3, min(12, len(compact) // 4))
            first_avg = sum(p["loss"] for p in compact[:window]) / window
            last_avg = sum(p["loss"] for p in compact[-window:]) / window
            delta = last_avg - first_avg
            info["loss_delta"] = round(delta, 6)
            if delta < -max(0.001, first_avg * 0.02):
                info["loss_trend"] = "稳定下降"
            elif delta > max(0.001, first_avg * 0.02):
                info["loss_trend"] = "上升波动"
            else:
                info["loss_trend"] = "小幅波动"

    lr_matches = re.findall(r"(?:lr|learning_rate)\s*[=:]\s*([0-9.eE+-]+)", source)
    if lr_matches:
        info["lr"] = lr_matches[-1]

    speed_matches = re.findall(r"([0-9.]+)\s*(?:it/s|s/it)", source)
    if speed_matches:
        info["speed"] = speed_matches[-1]

    tail_lines = lines[-120:]
    strong_error = first_matching_line(tail_lines, STRONG_ERROR_PATTERNS)
    warning = first_matching_line(tail_lines, WARNING_PATTERNS)
    if strong_error:
        info["strong_error"] = strong_error
    if warning:
        info["has_warning"] = True
        info["warning"] = warning

    return info


def anima_fast_progress_metrics(task: dict) -> dict:
    metadata = task.get("metadata") or {}
    if metadata.get("backend") != "anima-lora-fast":
        return {}
    raw_path = metadata.get("progress_jsonl")
    if not raw_path:
        return {}
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = (REPO / path).resolve()
    events = read_jsonl_events(path)
    metrics = metrics_from_anima_events(events)
    if metrics:
        metrics["progress_source"] = "anima_progress_jsonl"
    return metrics


# ---------------------------------------------------------------------------
# Status collection
# ---------------------------------------------------------------------------

def _training_output_dir() -> Path | None:
    """Return the resolved output_dir from the latest training config, or None."""
    config = latest_training_config()
    return resolve_repo_path(str(config.get("output_dir", "")))


def _task_output_dir(task: dict) -> Path | None:
    metadata = task.get("metadata") or {}
    output_dir = metadata.get("output_dir")
    if output_dir:
        return resolve_repo_path(str(output_dir))
    return None


def _preview_context(active: dict | None, train_config: dict) -> tuple[Path | None, str, int]:
    output_dir = _task_output_dir(active) if active else None
    if output_dir is None:
        output_dir = resolve_repo_path(str(train_config.get("output_dir", "")))

    output_name = str(train_config.get("output_name", "")).strip()
    config_output_dir = resolve_repo_path(str(train_config.get("output_dir", "")))
    if active and output_dir is not None and config_output_dir is not None and output_dir != config_output_dir:
        output_name = str((active.get("metadata") or {}).get("output_name", "")).strip()

    try:
        max_epochs = int(float(str(train_config.get("max_train_epochs", "")).strip()))
    except ValueError:
        max_epochs = 0
    return output_dir, output_name, max_epochs


def collect_status() -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    train_config = latest_training_config()
    status = {
        "time": now,
        "gui_online": False,
        "gui_warning": "",
        "state": "GUI 离线",
        "tasks": [],
        "active_task": None,
        "model_type": None,
        "log_lines": [],
        "metrics": {},
        "previews": [],
        "log_files": newest_files(LOG_DIR),
        "outputs": [],
        "outputs_primary": [],
        "outputs_other": [],
        "output_scope": "",
        "train_params": _extract_train_params(train_config),
        "tensorboard_loss": tensorboard_loss_scalars(),
        "gpu_info": gpu_info(),
    }

    gui_api = GUI_API
    try:
        tasks_payload, gui_api = fetch_gui_json("/train/tasks")
        tasks = api_data(tasks_payload).get("tasks", [])
        status["gui_online"] = True
        status["tasks"] = tasks
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        status["gui_warning"] = (
            f"主 GUI API 暂不可用（尝试 {', '.join(gui_api_candidates())}）：{exc}。"
            "训练参数、GPU 状态和 TensorBoard Loss 仍会继续同步。"
        )
        preview_dir, preview_name, max_epochs = _preview_context(None, train_config)
        try:
            status["previews"] = newest_preview_images(
                output_dir=preview_dir,
                output_name=preview_name,
                max_epochs=max_epochs,
            )
        except Exception:
            status["previews"] = []
        train_out = preview_dir or _training_output_dir()
        status.update(build_model_outputs(train_out))
        return status

    active = None
    if status["tasks"]:
        active = next((t for t in reversed(status["tasks"]) if t.get("status") == "RUNNING"), status["tasks"][-1])
    preview_dir, preview_name, max_epochs = _preview_context(active, train_config)
    try:
        status["previews"] = newest_preview_images(
            output_dir=preview_dir,
            output_name=preview_name,
            max_epochs=max_epochs,
        )
    except Exception:
        status["previews"] = []

    train_out = preview_dir or _training_output_dir()
    status.update(build_model_outputs(train_out))

    if not status["tasks"]:
        status["state"] = "空闲"
        status["model_type"] = None
        return status

    status["active_task"] = active
    state_map = {
        "RUNNING": "训练中",
        "FINISHED": "已结束",
        "FAILED": "失败",
        "TERMINATED": "已终止",
        "CREATED": "已创建，等待启动",
    }
    status["state"] = state_map.get(active.get("status"), active.get("status", "未知"))

    task_id = active.get("id")
    if task_id:
        try:
            tail_payload, _tail_url = fetch_gui_json(f"/train/log/tail/{task_id}?limit=2000")
            data = api_data(tail_payload)
            lines = data.get("lines", [])
            status["log_lines"] = lines
            status["model_type"] = infer_model_type(lines)
            try:
                stdout_metrics = parse_log(lines)
                anima_metrics = anima_fast_progress_metrics(active)
                if anima_metrics:
                    status["metrics"] = merge_anima_training_metrics(stdout_metrics, anima_metrics)
                    status["model_type"] = "Anima Fast LoRA"
                else:
                    status["metrics"] = stdout_metrics
                metrics = status["metrics"]
                task_status = active.get("status", "")
                update_progress_health(task_id, task_status, metrics)
                strong_error = bool(metrics.get("strong_error"))
                progress_stalled = bool(metrics.get("progress_stalled"))
                gpu_used = gpu_memory_used_mb()
                if gpu_used is not None:
                    metrics["gpu_memory_used_mb"] = gpu_used
                gpu_released = gpu_used is not None and gpu_used < GPU_IDLE_MEMORY_MB
                metrics["gpu_released"] = gpu_released
                metrics["has_error"] = strong_error and (
                    task_status != "RUNNING" or progress_stalled or gpu_released
                )
                if strong_error and not metrics["has_error"]:
                    metrics["needs_attention"] = True
            except Exception as exc:
                status["metrics"] = {}
                status["log_error"] = f"解析训练日志失败: {exc}"
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            status["log_error"] = f"读取训练日志失败: {exc}"

    return status


# ---------------------------------------------------------------------------
# Preview image sandboxing
# ---------------------------------------------------------------------------

def preview_image_path(raw_path: str) -> Path | None:
    try:
        decoded = unquote(raw_path)
        candidate = Path(decoded)
        if not candidate.is_absolute():
            candidate = (REPO / candidate).resolve()
        else:
            candidate = candidate.resolve()
        allowed_roots = [OUTPUT_DIR.resolve(), LOG_DIR.resolve()]
        train_out = _training_output_dir()
        if train_out is not None:
            allowed_roots.append(train_out.resolve())
        if not any(candidate == root or root in candidate.parents for root in allowed_roots):
            return None
        if not candidate.is_file() or candidate.suffix.lower() not in IMAGE_EXTENSIONS:
            return None
        return candidate
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Static file MIME types
# ---------------------------------------------------------------------------

STATIC_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        # Favicon
        if parsed.path == "/favicon.ico":
            self._serve_file(REPO / "assets" / "favicon.ico", "image/x-icon", cache=True)
            return

        # Logo
        if parsed.path == "/assets/logo.png":
            self._serve_file(REPO / "assets" / "logo.png", "image/png", cache=True)
            return

        # Static files (CSS, JS)
        if parsed.path.startswith("/static/"):
            filename = parsed.path[len("/static/"):]
            if ".." in filename or "/" in filename:
                self.send_error(403)
                return
            file_path = STATIC_DIR / filename
            content_type = STATIC_MIME.get(file_path.suffix.lower(), "application/octet-stream")
            self._serve_file(file_path, content_type, cache=False)
            return

        # Preview images
        if parsed.path == "/preview-image":
            params = parse_qs(parsed.query)
            image_path = preview_image_path((params.get("path") or [""])[0])
            if image_path is None:
                self.send_error(404)
                return
            content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
            self._serve_file(image_path, content_type, cache=False)
            return

        # API endpoint
        if self.path.startswith("/api/status"):
            payload = json.dumps(collect_status(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # Main page — serve index.html
        self._serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8", cache=False)

    def _serve_file(self, path: Path, content_type: str, cache: bool = False) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-cache")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        message = fmt % args
        is_success = " 200 " in message or " 304 " in message
        is_noisy_poll = (
            "GET /api/status" in message
            or "GET /preview-image" in message
            or "GET /assets/logo.png" in message
            or "GET /favicon.ico" in message
            or "GET /static/" in message
        )
        if is_success and is_noisy_poll:
            return
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {self.address_string()} {message}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Training monitor started at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()

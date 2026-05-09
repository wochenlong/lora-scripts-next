#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import mimetypes
import os
import re
import subprocess
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.error import URLError
from urllib.request import urlopen


HOST = "0.0.0.0"
PORT = 6008
GUI_API = "http://127.0.0.1:6006/api"
REPO = Path(__file__).resolve().parent
OUTPUT_DIR = REPO / "output"
LOG_DIR = REPO / "logs"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
PROGRESS_STALL_SECONDS = 120
GPU_IDLE_MEMORY_MB = 512
TASK_PROGRESS_STATE: dict[str, dict[str, float | int]] = {}

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


def fetch_json(url: str, timeout: float = 2.5) -> dict:
    with urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def api_data(payload: dict) -> dict:
    return payload.get("data") or {}


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
        })
    return out


def model_result_html(outputs: list[dict]) -> str:
    model_files = [
        item for item in outputs
        if Path(str(item.get("name", ""))).suffix.lower() in {".safetensors", ".ckpt", ".pt"}
    ]
    if not model_files:
        return '<div class="muted">暂无模型输出。训练完成后会在这里显示模型保存位置。</div>'

    latest = model_files[0]
    history = model_files[1:6]
    html_parts = [
        '<div class="result-card">',
        '<div class="label">最新模型</div>',
        f'<div class="result-name">{html.escape(str(latest["name"]))}</div>',
        f'<div class="muted">{html.escape(str(latest["size"]))} · {html.escape(str(latest["mtime"]))}</div>',
        f'<div class="result-path">{html.escape(str(latest["path"]))}</div>',
        '<div class="muted" id="resultDuration"></div>',
        '</div>',
    ]
    if history:
        html_parts.append('<details class="result-history"><summary>查看其他 checkpoint</summary><ul>')
        for item in history:
            html_parts.append(
                "<li>"
                f"<code>{html.escape(str(item['name']))}</code>"
                f"<div class='muted'>{html.escape(str(item['size']))} · {html.escape(str(item['mtime']))}</div>"
                "</li>"
            )
        html_parts.append("</ul></details>")
    return "\n".join(html_parts)


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
        for key in ("output_dir", "output_name", "max_train_epochs"):
            match = re.search(rf'^{key}\s*=\s*["\'](?P<value>.*?)["\']\s*$', text, flags=re.MULTILINE)
            if match:
                config[key] = match.group("value")
                continue
            match = re.search(rf'^{key}\s*=\s*(?P<value>[0-9.]+)\s*$', text, flags=re.MULTILINE)
            if match:
                config[key] = match.group("value")
        output_dir = config.get("output_dir")
        if output_dir:
            config["_config_path"] = str(config_path)
            return config
    return {}


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


def newest_preview_images(limit: int = 6) -> list[dict]:
    config = latest_training_config()
    output_dir = resolve_repo_path(str(config.get("output_dir", "")))
    output_name = str(config.get("output_name", "")).strip()
    try:
        max_epochs = int(float(str(config.get("max_train_epochs", "")).strip()))
    except ValueError:
        max_epochs = 0
    roots = []
    if output_dir is not None:
        roots.extend([output_dir / "sample", output_dir])
    else:
        roots.extend([OUTPUT_DIR / "sample", OUTPUT_DIR, LOG_DIR])

    newest_by_name: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if output_name and not p.name.startswith(output_name):
                continue
            old = newest_by_name.get(p.name)
            if old is None or p.stat().st_mtime >= old.stat().st_mtime:
                newest_by_name[p.name] = p

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
        rel = p.relative_to(REPO)
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
            "url": f"/preview-image?path={quote(str(rel))}",
            "role": role,
            "epoch": epoch,
            "max_epoch": max_epochs,
        })
    return out


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


def gpu_memory_used_mb() -> int | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            check=True,
            capture_output=True,
            text=True,
            timeout=1.2,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    total = 0
    for line in result.stdout.splitlines():
        try:
            total += int(line.strip())
        except ValueError:
            continue
    return total


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
    if "anima_train_network" in source or "lora_anima" in source or "qwen3" in source:
        return "Anima LoRA"
    if "flux_train_network" in source or "flux-lora" in source or "t5xxl" in source:
        return "Flux LoRA"
    if "sdxl_train_network" in source or "sdxl-lora" in source or "v_prediction" in source:
        return "SDXL LoRA"
    if "train_network.py" in source:
        return "LoRA"
    return "未知类型"


def parse_log(lines: list[str]) -> dict:
    text = "\n".join(lines[-5000:])
    joined = "\r".join(lines[-5000:])
    source = joined if "|" in joined else text
    info: dict[str, object] = {}

    # Training and sampling both use tqdm. Keep the main progress tied to
    # "steps:" so "Sampling:" cannot overwrite the total training progress.
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
        info.update({
            "percent": min(100.0, round(step * 100 / total, 2)) if total else int(m.group("pct")),
            "step": step,
            "total_steps": total,
            "eta": m.group("eta") or "",
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

    loss_matches = re.findall(r"(?:loss|train_loss)\s*[=:]\s*([0-9.eE+-]+)", source)
    if loss_matches:
        info["loss"] = loss_matches[-1]

    loss_points: list[dict[str, float | int]] = []
    for m in re.finditer(
        r"(?:^|[\r\n])steps:.*?\|\s*(?P<step>\d+)\s*/\s*(?P<total>\d+).*?(?:avr_loss|train_loss|loss)\s*[=:]\s*(?P<loss>[0-9.eE+-]+)",
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


def collect_status() -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = {
        "time": now,
        "gui_online": False,
        "state": "GUI 离线",
        "tasks": [],
        "active_task": None,
        "model_type": "未知类型",
        "log_lines": [],
        "metrics": {},
        "previews": newest_preview_images(),
        "outputs": newest_files(OUTPUT_DIR),
        "log_files": newest_files(LOG_DIR),
    }

    try:
        tasks_payload = fetch_json(f"{GUI_API}/train/tasks")
        tasks = api_data(tasks_payload).get("tasks", [])
        status["gui_online"] = True
        status["tasks"] = tasks
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        status["error"] = f"无法连接 6006 GUI API: {exc}"
        return status

    if not status["tasks"]:
        status["state"] = "空闲"
        return status

    active = next((t for t in reversed(status["tasks"]) if t.get("status") == "RUNNING"), status["tasks"][-1])
    status["active_task"] = active
    state_map = {
        "RUNNING": "训练中",
        "FINISHED": "已结束",
        "TERMINATED": "已终止",
        "CREATED": "已创建，等待启动",
    }
    status["state"] = state_map.get(active.get("status"), active.get("status", "未知"))

    task_id = active.get("id")
    if task_id:
        try:
            tail_payload = fetch_json(f"{GUI_API}/train/log/tail/{task_id}?limit=5000")
            data = api_data(tail_payload)
            lines = data.get("lines", [])
            status["log_lines"] = lines
            status["model_type"] = infer_model_type(lines)
            try:
                status["metrics"] = parse_log(lines)
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


def render_page(status: dict) -> bytes:
    metrics = status.get("metrics", {})
    task = status.get("active_task") or {}
    lines = status.get("log_lines") or []

    cards = [
        ("模型类型", status.get("model_type", "-")),
        ("状态", status.get("state", "-")),
        ("进度", progress_text(metrics)),
        ("Epoch", metrics.get("epoch", "-")),
        ("耗时", metrics.get("duration") or metrics.get("elapsed", "-")),
        ("剩余", metrics.get("eta") if status.get("state") == "训练中" else "-"),
        ("Loss", metrics.get("loss", "-")),
    ]
    card_html = "\n".join(
        f'<div class="card"><div class="label">{html.escape(k)}</div><div class="value">{html.escape(str(v or "-"))}</div></div>'
        for k, v in cards
    )

    log_html = html.escape("\n".join(lines[-180:]) or "暂无训练日志。")
    result_html = model_result_html(status.get("outputs") or [])
    error = status.get("error") or status.get("log_error") or ""

    initial_status = html.escape(json.dumps(status, ensure_ascii=False), quote=False)
    body = f"""<!doctype html>
<html lang="zh-Hans">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>训练监控 - 6008</title>
  <style>
    :root {{ color-scheme: dark; --bg:#0b1020; --panel:#121a2e; --line:#26324d; --text:#e5edf8; --muted:#91a0b8; --ok:#34d399; --warn:#fbbf24; --err:#fb7185; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    header {{ padding:16px 20px; border-bottom:1px solid var(--line); background:#0f172a; display:flex; justify-content:space-between; gap:12px; align-items:center; }}
    h1 {{ margin:0; font-size:18px; }}
    .muted {{ color:var(--muted); font-size:12px; }}
    main {{ padding:18px; display:grid; gap:18px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }}
    .card,.panel {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; }}
    .hero {{ display:grid; gap:12px; padding:16px; background:linear-gradient(135deg,#172033,#101827); border:1px solid var(--line); border-radius:14px; }}
    .hero-top {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-end; flex-wrap:wrap; }}
    .hero-title {{ font-size:22px; font-weight:750; }}
    .hero-copy {{ color:var(--muted); }}
    .progress-track {{ width:100%; height:14px; border-radius:999px; background:#050816; overflow:hidden; border:1px solid var(--line); }}
    .progress-fill {{ height:100%; width:0%; background:linear-gradient(90deg,#38bdf8,#34d399); transition:width .3s ease; }}
    .sample-progress {{ display:grid; gap:6px; }}
    .sample-progress .hero-copy {{ font-size:12px; }}
    .sample-progress .progress-track {{ height:5px; opacity:.9; }}
    .sample-progress .progress-fill {{ background:linear-gradient(90deg,#fbbf24,#fb7185); }}
    .loss-summary {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; color:var(--muted); font-size:13px; }}
    .pill {{ display:inline-flex; align-items:center; border:1px solid var(--line); border-radius:999px; padding:3px 8px; background:#0b1224; color:var(--text); }}
    .pill.good {{ color:#86efac; border-color:#166534; background:#052e1a; }}
    .loss-chart {{ width:100%; height:96px; border:1px solid var(--line); border-radius:12px; background:#050816; }}
    .trend-chart {{ width:100%; aspect-ratio:16/10; height:auto; display:block; border:1px solid var(--line); border-radius:12px; background:#050816; }}
    .loss-line {{ fill:none; stroke:#34d399; stroke-width:2; vector-effect:non-scaling-stroke; stroke-linejoin:round; stroke-linecap:round; }}
    .loss-area {{ fill:rgba(52,211,153,.14); }}
    .loss-grid {{ stroke:#1e2a44; stroke-width:1; stroke-dasharray:3 4; }}
    .loss-baseline {{ stroke:#3a486a; stroke-width:1; stroke-dasharray:6 6; }}
    .loss-axis-text {{ fill:#7286a3; font:11px ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }}
    .loss-axis-text.right {{ text-anchor:end; }}
    .loss-axis-text.center {{ text-anchor:middle; }}
    .loss-current-dot {{ fill:#34d399; stroke:#0b1224; stroke-width:2; }}
    .loss-current-label-bg {{ fill:rgba(11,18,36,.92); stroke:#34d399; stroke-width:1; }}
    .loss-current-label-text {{ fill:#bbf7d0; font:600 12px ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }}
    .trend-layout {{ display:grid; grid-template-columns:minmax(0,1fr) 240px; gap:14px; align-items:end; max-width:1080px; }}
    @media (max-width: 820px) {{ .trend-layout {{ grid-template-columns:1fr; max-width:none; }} }}
    .trend-stats {{ display:grid; grid-template-columns:1fr; gap:8px; align-content:start; }}
    .trend-stat {{ background:#0b1224; border:1px solid var(--line); border-radius:10px; padding:9px 12px; display:flex; align-items:baseline; justify-content:space-between; gap:10px; }}
    .trend-stat .label {{ color:var(--muted); font-size:11px; letter-spacing:.4px; text-transform:uppercase; flex:0 0 auto; }}
    .trend-stat .value {{ font-size:16px; font-weight:700; color:var(--text); line-height:1.2; font-variant-numeric:tabular-nums; text-align:right; }}
    .trend-stat .sub {{ display:none; }}
    .trend-stat.delta-down .value {{ color:#86efac; }}
    .trend-stat.delta-up .value {{ color:#fbbf24; }}
    .trend-stat .pill {{ font-size:12px; padding:2px 8px; }}
    @media (max-width: 820px) {{ .trend-stats {{ grid-template-columns:repeat(2,1fr); }} }}
    .card {{ padding:14px; }}
    .label {{ color:var(--muted); font-size:12px; margin-bottom:6px; }}
    .value {{ font-size:18px; font-weight:650; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .panel {{ padding:14px; }}
    .panel h2 {{ margin:0; font-size:15px; }}
    .trend-headline {{ font-size:20px; font-weight:750; margin:4px 0; }}
    .trend-copy {{ color:var(--muted); font-size:13px; margin-bottom:10px; }}
    .result-card {{ display:grid; gap:6px; padding:12px; border:1px solid var(--line); border-radius:12px; background:#050816; }}
    .result-name {{ font-size:18px; font-weight:750; }}
    .result-path {{ color:#bfdbfe; font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace; word-break:break-all; }}
    .result-history {{ margin-top:10px; }}
    .panel-head {{ display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }}
    .log-tools {{ display:flex; align-items:center; gap:10px; }}
    .follow-state {{ color:var(--ok); font-size:12px; }}
    .follow-state.paused {{ color:var(--warn); }}
    button {{ border:1px solid var(--line); border-radius:999px; padding:6px 10px; background:#172033; color:var(--text); cursor:pointer; }}
    button:hover {{ border-color:#60a5fa; }}
    button.primary {{ border-color:#38bdf8; background:linear-gradient(135deg,#2563eb,#0891b2); color:white; font-weight:700; }}
    button.hidden {{ display:none; }}
    details summary {{ cursor:pointer; color:var(--muted); }}
    .details-body {{ margin-top:12px; }}
    .preview-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; max-width:980px; }}
    .preview-card {{ overflow:hidden; border:1px solid var(--line); border-radius:12px; background:#050816; position:relative; }}
    .preview-card img {{ display:block; width:100%; height:180px; object-fit:cover; background:#050816; }}
    .preview-meta {{ padding:8px 10px; color:var(--muted); font-size:12px; }}
    .preview-role {{ position:absolute; left:8px; top:8px; display:inline-flex; padding:2px 7px; border-radius:999px; background:rgba(15,23,42,.82); color:#bfdbfe; border:1px solid rgba(191,219,254,.35); font-size:11px; backdrop-filter:blur(4px); }}
    .preview-step {{ color:var(--text); font-size:15px; font-weight:800; line-height:1.2; }}
    .preview-epoch {{ color:#bfdbfe; font-size:12px; font-weight:650; margin-top:2px; }}
    .preview-file {{ color:var(--muted); font:11px/1.35 ui-monospace,SFMono-Regular,Consolas,monospace; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .preview-hidden {{ padding:14px; border:1px dashed var(--line); border-radius:10px; background:#0b1224; color:var(--muted); }}
    .preview-hidden strong {{ display:block; color:var(--text); margin-bottom:4px; }}
    .privacy-note {{ color:var(--muted); font-size:12px; }}
    pre {{ margin:0; padding:12px; border-radius:10px; background:#050816; color:#dbeafe; overflow:auto; max-height:56vh; white-space:pre-wrap; word-break:break-word; font:12px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace; }}
    ul {{ margin:0; padding-left:18px; }}
    li {{ margin:6px 0; }}
    code {{ color:#bfdbfe; }}
    .err {{ color:var(--err); }}
  </style>
</head>
<body>
  <header>
    <div><h1>训练监控</h1><div class="muted">端口 6008，每 2 秒自动更新</div></div>
    <div class="muted" id="updatedAt">{html.escape(status.get("time", ""))}</div>
  </header>
  <main>
    <div class="panel err" id="errorBox" style="display:{'block' if error else 'none'}">{html.escape(error)}</div>
    <section class="hero">
      <div class="hero-top">
        <div>
          <div class="hero-title" id="heroTitle">训练状态读取中</div>
          <div class="hero-copy" id="heroCopy">正在同步训练状态。</div>
        </div>
        <div class="hero-title" id="heroPercent">-</div>
      </div>
      <div class="progress-track"><div class="progress-fill" id="progressFill"></div></div>
      <div class="loss-summary" id="lossSummary">Loss 曲线等待数据。</div>
      <div class="sample-progress" id="sampleProgress">
        <div class="hero-copy" id="sampleProgressText">预览图生成进度：等待下一次采样</div>
        <div class="progress-track"><div class="progress-fill" id="sampleProgressFill"></div></div>
      </div>
    </section>
    <section class="grid" id="cards">{card_html}</section>
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>训练预览图</h2>
          <div class="privacy-note">默认关闭，开启后仅当前浏览器加载图片，保护公开端口下的训练隐私。</div>
        </div>
        <button id="togglePreview" type="button">开启预览图</button>
      </div>
      <div id="previewArea"><div class="preview-hidden"><strong>预览图未加载</strong>点击右侧“开启预览图”后，当前浏览器才会加载训练图片。</div></div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Loss 趋势</h2>
          <div class="privacy-note">相对初始 Loss 展示，更适合判断训练是否稳定收敛。</div>
        </div>
      </div>
      <div class="trend-headline" id="lossTrendHeadline">等待 Loss 数据</div>
      <div class="trend-copy" id="lossTrendCopy">开始训练后会显示相对初始值的下降趋势。</div>
      <div class="trend-layout">
        <svg class="trend-chart" id="lossTrendChart" viewBox="0 0 720 450" preserveAspectRatio="xMidYMid meet" aria-label="Loss 相对趋势"></svg>
        <div class="trend-stats" id="lossTrendStats">
          <div class="trend-stat"><span class="label">当前</span><span class="value" id="statLossCurrent">-</span></div>
          <div class="trend-stat"><span class="label">最低</span><span class="value" id="statLossMin">-</span></div>
          <div class="trend-stat"><span class="label">初始</span><span class="value" id="statLossBaseline">-</span></div>
          <div class="trend-stat"><span class="label">下降</span><span class="value" id="statLossDrop">-</span></div>
          <div class="trend-stat" id="statDeltaCard"><span class="label">最近 Δ</span><span class="value" id="statLossDelta">-</span></div>
          <div class="trend-stat"><span class="label">趋势</span><span class="pill" id="statLossTrendPill">等待数据</span></div>
        </div>
      </div>
    </section>
    <details class="panel" id="logDetails">
      <summary id="logSummary">训练日志</summary>
      <div class="details-body">
        <div class="log-tools">
          <span class="follow-state" id="followState">自动跟随最新</span>
          <button class="hidden" id="jumpLatest" type="button">回到最新</button>
        </div>
        <div style="height:10px"></div>
        <pre id="logBox">{log_html}</pre>
      </div>
    </details>
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>训练结果</h2>
          <div class="privacy-note">训练完成后，最新模型和保存位置会显示在这里。</div>
        </div>
      </div>
      <div id="resultFiles">{result_html}</div>
    </section>
  </main>
  <script id="initialStatus" type="application/json">{initial_status}</script>
  <script>
    const logBox = document.getElementById("logBox");
    const followState = document.getElementById("followState");
    const jumpLatest = document.getElementById("jumpLatest");
    const togglePreview = document.getElementById("togglePreview");
    const logDetails = document.getElementById("logDetails");
    const logSummary = document.getElementById("logSummary");
    let autoFollow = true;
    let lastLogText = "";
    let lastPreviewKey = "";
    let previewEnabled = localStorage.getItem("loraMonitorPreviewEnabled") === "1";

    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, function(ch) {{
        return ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }})[ch];
      }});
    }}

    function isNearBottom(el) {{
      return el.scrollHeight - el.scrollTop - el.clientHeight < 64;
    }}

    function scrollToLatest() {{
      logBox.scrollTop = logBox.scrollHeight;
    }}

    function setAutoFollow(value) {{
      autoFollow = value;
      followState.textContent = autoFollow ? "自动跟随最新" : "已暂停，正在查看历史日志";
      followState.classList.toggle("paused", !autoFollow);
      jumpLatest.classList.toggle("hidden", autoFollow);
    }}

    logBox.addEventListener("scroll", function() {{
      setAutoFollow(isNearBottom(logBox));
    }});

    jumpLatest.addEventListener("click", function() {{
      setAutoFollow(true);
      scrollToLatest();
    }});

    togglePreview.addEventListener("click", function() {{
      previewEnabled = !previewEnabled;
      localStorage.setItem("loraMonitorPreviewEnabled", previewEnabled ? "1" : "0");
      lastPreviewKey = "";
      renderPreviewToggle();
      pollStatus();
    }});

    function progressText(metrics) {{
      if (!metrics || metrics.step === undefined) return "-";
      let text = String(metrics.step) + "/" + String(metrics.total_steps ?? "-");
      if (metrics.percent !== undefined) text += " (" + String(metrics.percent) + "%)";
      return text;
    }}

    function renderCards(status) {{
      const metrics = status.metrics || {{}};
      const task = status.active_task || {{}};
      const cards = [
        ["模型类型", status.model_type || "-"],
        ["状态", status.state || "-"],
        ["进度", progressText(metrics)],
        ["Epoch", metrics.epoch || "-"],
        ["耗时", metrics.duration || metrics.elapsed || "-"],
        ["剩余", status.state === "训练中" ? (metrics.eta || "-") : "-"],
        ["Loss", metrics.loss || "-"],
      ];
      document.getElementById("cards").innerHTML = cards.map(function(card) {{
        return '<div class="card"><div class="label">' + escapeHtml(card[0]) + '</div><div class="value">' + escapeHtml(card[1] || "-") + '</div></div>';
      }}).join("");
    }}

    function renderHero(status) {{
      const metrics = status.metrics || {{}};
      const modelType = status.model_type || "训练";
      const state = status.state || "-";
      const pct = Number(metrics.percent || 0);
      const hasPct = Number.isFinite(pct) && pct > 0;
      const error = status.error || status.log_error || metrics.has_error;
      const attention = metrics.needs_attention || metrics.progress_stalled;
      let title = modelType + " " + state;
      let copy = "正在等待训练状态。";
      const lossText = metrics.loss ? "Loss " + metrics.loss : "";
      const trendText = metrics.loss_trend ? "，" + metrics.loss_trend : "";

      if (error) {{
        title = "训练需要关注";
        copy = "检测到强错误信号，并结合任务状态判断训练可能已异常退出。";
      }} else if (attention) {{
        title = "训练需要关注";
        copy = metrics.progress_stalled
          ? "训练 step 已长时间未增长，请观察显存和日志。"
          : "日志中出现强错误信号，但训练仍在推进，先不自动展开日志。";
      }} else if (state === "训练中") {{
        copy = modelType + " 训练中" +
          (metrics.elapsed ? "，已训练 " + metrics.elapsed : "") +
          (lossText ? "，" + lossText + trendText : "") +
          (metrics.eta ? "，预计还需 " + metrics.eta + "。" : "。");
      }} else if (state === "已结束") {{
        copy = modelType + " 训练已完成" +
          (metrics.duration ? "，总耗时 " + metrics.duration : "") +
          (lossText ? "，" + lossText + trendText : "") + "，最新模型已保存到输出目录。";
      }} else if (state === "空闲") {{
        copy = "当前没有训练任务。";
      }}

      document.getElementById("heroTitle").textContent = title;
      document.getElementById("heroCopy").textContent = copy;
      document.getElementById("heroPercent").textContent = hasPct ? pct.toFixed(pct % 1 === 0 ? 0 : 1) + "%" : "-";
      document.getElementById("progressFill").style.width = Math.max(0, Math.min(100, pct || 0)) + "%";
      renderSamplingProgress(metrics.sampling, status);
    }}

    function renderSamplingProgress(sampling, status) {{
      const text = document.getElementById("sampleProgressText");
      const fill = document.getElementById("sampleProgressFill");
      if (!sampling || !sampling.active) {{
        fill.style.width = sampling && sampling.percent >= 100 ? "100%" : "0%";
        if (sampling && sampling.percent >= 100) {{
          const atStep = sampling.train_step ? "（训练 step " + sampling.train_step + "）" : "";
          text.textContent = "预览图生成进度：最近一次采样已完成" + atStep;
        }} else if (status && status.state === "训练中") {{
          text.textContent = "预览图生成进度：等待下一次采样";
        }} else {{
          text.textContent = "预览图生成进度：暂无采样任务";
        }}
        return;
      }}
      const pct = Number(sampling.percent || 0);
      fill.style.width = Math.max(0, Math.min(100, pct)) + "%";
      const atStep = sampling.train_step ? "（训练 step " + sampling.train_step + "）" : "";
      text.textContent = "预览图生成中" + atStep + "：" + sampling.step + "/" + sampling.total_steps + "（" + pct + "%）" + (sampling.eta ? "，预计 " + sampling.eta : "");
    }}

    function fmtLoss(v) {{
      const n = Number(v);
      if (!Number.isFinite(n)) return "-";
      const abs = Math.abs(n);
      if (abs >= 1) return n.toFixed(3);
      if (abs >= 0.01) return n.toFixed(4);
      return n.toExponential(2);
    }}

    function renderLossChart(metrics) {{
      const trendChart = document.getElementById("lossTrendChart");
      const trendHeadline = document.getElementById("lossTrendHeadline");
      const trendCopy = document.getElementById("lossTrendCopy");
      const summary = document.getElementById("lossSummary");
      const points = (metrics && metrics.loss_points) || [];
      const relativePoints = (metrics && metrics.relative_loss_points) || [];
      const trend = metrics && metrics.loss_trend ? metrics.loss_trend : "等待趋势";
      const loss = metrics && metrics.loss ? metrics.loss : "-";
      const drop = Number(metrics && metrics.loss_drop_percent);
      const trendClass = trend === "稳定下降" ? "pill good" : "pill";
      const dropText = Number.isFinite(drop) ? " · 较初始下降 " + Math.max(0, drop).toFixed(1) + "%" : "";
      summary.innerHTML = '<span>当前 Loss：<strong>' + escapeHtml(loss) + '</strong>' + escapeHtml(dropText) + '</span>' +
        '<span class="' + trendClass + '">' + escapeHtml(trend) + '</span>' +
        '<span class="muted">用于截图说明训练是否稳定</span>';

      const statBaseline = document.getElementById("statLossBaseline");
      const statCurrent = document.getElementById("statLossCurrent");
      const statMin = document.getElementById("statLossMin");
      const statDelta = document.getElementById("statLossDelta");
      const statDeltaCard = document.getElementById("statDeltaCard");
      const statDrop = document.getElementById("statLossDrop");
      const statTrendPill = document.getElementById("statLossTrendPill");

      const baseline = Number(metrics && metrics.loss_baseline);
      const current = Number(metrics && metrics.loss_current);
      const lossDelta = Number(metrics && metrics.loss_delta);
      let minLoss = NaN, minStep = null;
      for (const p of points) {{
        const v = Number(p && p.loss);
        if (Number.isFinite(v) && (!Number.isFinite(minLoss) || v < minLoss)) {{
          minLoss = v;
          minStep = Number(p.step);
        }}
      }}

      statBaseline.textContent = Number.isFinite(baseline) ? fmtLoss(baseline) : "-";
      statCurrent.textContent = Number.isFinite(current) ? fmtLoss(current) : (loss !== "-" ? loss : "-");
      statMin.textContent = Number.isFinite(minLoss) ? fmtLoss(minLoss) : "-";
      statMin.title = (Number.isFinite(minLoss) && minStep != null) ? ("出现在 step " + minStep) : "";

      statDeltaCard.classList.remove("delta-down", "delta-up");
      if (Number.isFinite(lossDelta)) {{
        const sign = lossDelta > 0 ? "+" : (lossDelta < 0 ? "−" : "");
        statDelta.textContent = sign + fmtLoss(Math.abs(lossDelta));
        if (lossDelta < -1e-9) statDeltaCard.classList.add("delta-down");
        else if (lossDelta > 1e-9) statDeltaCard.classList.add("delta-up");
      }} else {{
        statDelta.textContent = "-";
      }}

      statDrop.textContent = Number.isFinite(drop) ? (Math.max(0, drop).toFixed(1) + "%") : "-";
      statTrendPill.className = trendClass;
      statTrendPill.textContent = trend;

      if (points.length < 2) {{
        trendChart.innerHTML = '<text x="20" y="74" fill="#91a0b8" font-size="13">等待更多 loss 数据...</text>';
        trendHeadline.textContent = "等待 Loss 数据";
        trendCopy.textContent = "训练开始后会显示相对初始值的下降趋势。";
        return;
      }}

      if (relativePoints.length >= 2) {{
        const relValues = relativePoints.map(function(p) {{ return Number(p.relative); }}).filter(Number.isFinite);
        const currentRel = relValues[relValues.length - 1];
        const relativeDrop = Math.max(0, 100 - currentRel);
        trendHeadline.textContent = "当前 Loss " + loss + " · 较初始下降 " + relativeDrop.toFixed(1) + "% · " + trend;
        trendCopy.textContent = "以训练初期 Loss 为 100%，曲线越往下说明相对初始值下降越明显。";

        const tw = 720;
        const th = 450;
        const padTop = 26;
        const padRight = 28;
        const padBottom = 44;
        const padLeft = 60;
        const plotW = tw - padLeft - padRight;
        const plotH = th - padTop - padBottom;

        const minRelActual = Math.min.apply(null, relValues);
        const yMax = 100;
        let yMin = Math.max(0, Math.floor((minRelActual - 4) / 5) * 5);
        if (yMin >= yMax) yMin = yMax - 5;
        const yTicks = 5;
        const yStep = (yMax - yMin) / (yTicks - 1);

        const stepValues = relativePoints.map(function(p) {{ return Number(p.step) || 0; }});
        const xMin = stepValues[0];
        const xMax = stepValues[stepValues.length - 1];
        const xRange = Math.max(1, xMax - xMin);
        const xTicks = Math.min(6, Math.max(2, relativePoints.length));

        function xToPx(step) {{
          return padLeft + ((step - xMin) / xRange) * plotW;
        }}
        function yToPx(rel) {{
          return padTop + (1 - (rel - yMin) / Math.max(1, yMax - yMin)) * plotH;
        }}

        let gridSvg = "";
        for (let i = 0; i < yTicks; i++) {{
          const v = yMin + i * yStep;
          const y = yToPx(v).toFixed(1);
          const cls = Math.abs(v - 100) < 0.01 ? "loss-baseline" : "loss-grid";
          gridSvg += '<line class="' + cls + '" x1="' + padLeft + '" y1="' + y +
                     '" x2="' + (padLeft + plotW) + '" y2="' + y + '"></line>';
          gridSvg += '<text class="loss-axis-text right" x="' + (padLeft - 8) + '" y="' + (Number(y) + 4) +
                     '">' + v.toFixed(0) + '%</text>';
        }}
        for (let i = 0; i < xTicks; i++) {{
          const stepVal = xMin + (xRange * i) / Math.max(1, xTicks - 1);
          const x = xToPx(stepVal).toFixed(1);
          gridSvg += '<line class="loss-grid" x1="' + x + '" y1="' + padTop + '" x2="' + x +
                     '" y2="' + (padTop + plotH) + '"></line>';
          gridSvg += '<text class="loss-axis-text center" x="' + x + '" y="' + (padTop + plotH + 22) +
                     '">' + Math.round(stepVal) + '</text>';
        }}

        const tcoords = relativePoints.map(function(p) {{
          return [xToPx(Number(p.step) || 0), yToPx(Number(p.relative))];
        }});
        const tline = tcoords.map(function(pt, i) {{
          return (i === 0 ? "M" : "L") + pt[0].toFixed(1) + " " + pt[1].toFixed(1);
        }}).join(" ");
        const lastX = tcoords[tcoords.length - 1][0].toFixed(1);
        const firstX = tcoords[0][0].toFixed(1);
        const baseY = (padTop + plotH).toFixed(1);
        const tarea = tline + " L " + lastX + " " + baseY + " L " + firstX + " " + baseY + " Z";

        const cx = tcoords[tcoords.length - 1][0];
        const cy = tcoords[tcoords.length - 1][1];
        const labelText = currentRel.toFixed(1) + "%";
        const labelW = labelText.length * 7 + 14;
        let labelX = cx + 10;
        if (labelX + labelW > padLeft + plotW) labelX = cx - labelW - 10;
        const labelY = Math.min(Math.max(cy - 12, padTop + 4), padTop + plotH - 24);

        const axisTitleSvg =
          '<text class="loss-axis-text" x="' + padLeft + '" y="' + (padTop - 10) + '">相对初始 Loss</text>' +
          '<text class="loss-axis-text right" x="' + (padLeft + plotW) + '" y="' + (th - 8) + '">step</text>';

        trendChart.innerHTML =
          gridSvg +
          '<path class="loss-area" d="' + tarea + '"></path>' +
          '<path class="loss-line" d="' + tline + '"></path>' +
          '<circle class="loss-current-dot" cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="4.5"></circle>' +
          '<rect class="loss-current-label-bg" x="' + labelX.toFixed(1) + '" y="' + labelY.toFixed(1) +
          '" width="' + labelW + '" height="20" rx="4" ry="4"></rect>' +
          '<text class="loss-current-label-text" x="' + (labelX + labelW / 2).toFixed(1) + '" y="' + (labelY + 14).toFixed(1) +
          '" text-anchor="middle">' + labelText + '</text>' +
          axisTitleSvg;
      }}

    }}

    function renderFiles(files) {{
      if (!files || files.length === 0) return '<div class="muted">暂无文件</div>';
      return "<ul>" + files.map(function(item) {{
        return "<li><code>" + escapeHtml(item.name) + "</code><div class='muted'>" +
          escapeHtml(item.size) + " · " + escapeHtml(item.mtime) + "<br>" +
          escapeHtml(item.path) + "</div></li>";
      }}).join("") + "</ul>";
    }}

    function renderResult(files) {{
      const modelFiles = (files || []).filter(function(item) {{
        return /\\.(safetensors|ckpt|pt)$/i.test(item.name || "");
      }});
      if (modelFiles.length === 0) {{
        return '<div class="muted">暂无模型输出。训练完成后会在这里显示模型保存位置。</div>';
      }}
      const latest = modelFiles[0];
      const history = modelFiles.slice(1, 6);
      let html = '<div class="result-card">' +
        '<div class="label">最新模型</div>' +
        '<div class="result-name">' + escapeHtml(latest.name) + '</div>' +
        '<div class="muted">' + escapeHtml(latest.size) + ' · ' + escapeHtml(latest.mtime) + '</div>' +
        '<div class="result-path">' + escapeHtml(latest.path) + '</div>' +
        '</div>';
      if (history.length > 0) {{
        html += '<details class="result-history"><summary>查看其他 checkpoint</summary><ul>' +
          history.map(function(item) {{
            return '<li><code>' + escapeHtml(item.name) + '</code><div class="muted">' +
              escapeHtml(item.size) + ' · ' + escapeHtml(item.mtime) + '</div></li>';
          }}).join("") + '</ul></details>';
      }}
      return html;
    }}

    function renderResultDuration(metrics) {{
      const el = document.getElementById("resultDuration");
      if (!el) return;
      const duration = metrics && (metrics.duration || metrics.elapsed);
      el.textContent = duration ? "本次训练耗时：" + duration : "";
    }}

    function renderPreviewToggle() {{
      togglePreview.textContent = previewEnabled ? "关闭预览图" : "开启预览图";
      togglePreview.classList.toggle("primary", !previewEnabled);
      if (!previewEnabled) {{
        document.getElementById("previewArea").innerHTML = '<div class="preview-hidden"><strong>预览图未加载</strong>点击右侧“开启预览图”后，当前浏览器才会加载训练图片；关闭时不会请求图片，适合公开端口截图。</div>';
        lastPreviewKey = "";
      }}
    }}

    function previewProgressParts(item, metrics) {{
      const epoch = Number(item.epoch);
      const maxEpoch = Number(item.max_epoch);
      const totalSteps = Number(metrics && metrics.total_steps);
      if (Number.isFinite(epoch)) {{
        let stepText = epoch === 0 ? "Step 0" : "";
        if (Number.isFinite(maxEpoch) && maxEpoch > 0 && Number.isFinite(totalSteps) && totalSteps > 0) {{
          const step = Math.round(totalSteps * epoch / maxEpoch);
          stepText = "Step " + step;
        }}
        return {{ step: stepText || "Step -", epoch: "Epoch " + epoch }};
      }}
      return {{ step: item.role || "预览图", epoch: "Epoch -" }};
    }}

    function renderPreviews(previews, metrics) {{
      const area = document.getElementById("previewArea");
      if (!previewEnabled) {{
        renderPreviewToggle();
        return;
      }}
      if (!previews || previews.length === 0) {{
        if (lastPreviewKey !== "__empty__") {{
          area.innerHTML = '<div class="muted">还没有训练预览图。通常会在第一次采样后出现在这里。</div>';
          lastPreviewKey = "__empty__";
        }}
        return;
      }}
      const previewKey = previews.map(function(item) {{
        return item.url + "|" + item.mtime + "|" + item.size;
      }}).join("||");
      if (previewKey === lastPreviewKey) return;
      lastPreviewKey = previewKey;
      area.innerHTML = '<div class="preview-grid">' + previews.map(function(item) {{
        const progress = previewProgressParts(item, metrics || {{}});
        return '<div class="preview-card">' +
          (item.role ? '<span class="preview-role">' + escapeHtml(item.role) + '</span>' : '') +
          '<img loading="lazy" src="' + escapeHtml(item.url) + '" alt="' + escapeHtml(item.name) + '">' +
          '<div class="preview-meta">' +
          '<div class="preview-step">' + escapeHtml(progress.step) + '</div>' +
          '<div class="preview-epoch">' + escapeHtml(progress.epoch) + '</div>' +
          '<div class="preview-file" title="' + escapeHtml(item.name) + '">' + escapeHtml(item.name) + '</div></div>' +
          '</div>';
      }}).join("") + '</div>';
    }}

    function renderStatus(status) {{
      document.getElementById("updatedAt").textContent = status.time || "";
      const metrics = status.metrics || {{}};
      const error = status.error || status.log_error || "";
      const errorBox = document.getElementById("errorBox");
      errorBox.textContent = error;
      errorBox.style.display = error ? "block" : "none";
      renderHero(status);
      renderCards(status);
      renderLossChart(metrics);
      renderPreviews(status.previews, metrics);
      document.getElementById("resultFiles").innerHTML = renderResult(status.outputs);
      renderResultDuration(metrics);

      const logLines = status.log_lines || [];
      const hasLogError = Boolean(error || metrics.has_error);
      const hasLogWarning = Boolean(metrics.needs_attention || metrics.progress_stalled || metrics.has_warning);
      logSummary.textContent = hasLogError
        ? "训练日志（检测到错误，已自动展开）"
        : (hasLogWarning ? "训练日志（有警告，未自动展开）" : "训练日志（正常，最近 " + logLines.length + " 行）");
      if (hasLogError) logDetails.open = true;

      const wasNearBottom = autoFollow || isNearBottom(logBox);
      const logText = logLines.slice(-180).join("\\n") || "暂无训练日志。";
      if (logText !== lastLogText) {{
        logBox.textContent = logText;
        lastLogText = logText;
        if (wasNearBottom) scrollToLatest();
      }}
    }}

    async function pollStatus() {{
      try {{
        const resp = await fetch("/api/status?ts=" + Date.now(), {{ cache: "no-store" }});
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        renderStatus(await resp.json());
      }} catch (err) {{
        const errorBox = document.getElementById("errorBox");
        errorBox.textContent = "刷新监控状态失败: " + err;
        errorBox.style.display = "block";
      }}
    }}

    renderStatus(JSON.parse(document.getElementById("initialStatus").textContent));
    renderPreviewToggle();
    scrollToLatest();
    setInterval(pollStatus, 2000);
  </script>
</body>
</html>"""
    return body.encode("utf-8")


def progress_text(metrics: dict) -> str:
    if "step" not in metrics:
        return "-"
    text = f'{metrics.get("step")}/{metrics.get("total_steps")}'
    if "percent" in metrics:
        text += f' ({metrics["percent"]}%)'
    return text


def file_list(files: list[dict]) -> str:
    if not files:
        return '<div class="muted">暂无文件</div>'
    items = []
    for item in files:
        items.append(
            "<li>"
            f"<code>{html.escape(item['name'])}</code>"
            f"<div class='muted'>{html.escape(item['size'])} · {html.escape(item['mtime'])}<br>{html.escape(item['path'])}</div>"
            "</li>"
        )
    return "<ul>" + "\n".join(items) + "</ul>"


def preview_image_path(raw_path: str) -> Path | None:
    try:
        rel = Path(unquote(raw_path))
        candidate = (REPO / rel).resolve()
        allowed_roots = (OUTPUT_DIR.resolve(), LOG_DIR.resolve())
        if not any(candidate == root or root in candidate.parents for root in allowed_roots):
            return None
        if not candidate.is_file() or candidate.suffix.lower() not in IMAGE_EXTENSIONS:
            return None
        return candidate
    except OSError:
        return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/preview-image":
            params = parse_qs(parsed.query)
            image_path = preview_image_path((params.get("path") or [""])[0])
            if image_path is None:
                self.send_error(404)
                return
            payload = image_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(image_path.name)[0] or "application/octet-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if self.path.startswith("/api/status"):
            payload = json.dumps(collect_status(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        payload = render_page(collect_status())
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {self.address_string()} {fmt % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Training monitor started at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()

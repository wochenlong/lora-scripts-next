from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any


_LOSS_KEYS = (
    "loss/average",
    "loss/current",
    "loss",
    "train_loss",
    "avr_loss",
)


def read_jsonl_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            events.append(data)
    return events


def _pick_loss(event: dict[str, Any]) -> Any:
    for key in _LOSS_KEYS:
        if key in event and event[key] is not None:
            return event[key]
    return None


def _format_seconds(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}小时{minutes:02d}分{secs:02d}秒"
    if minutes:
        return f"{minutes}分{secs:02d}秒"
    return f"{secs}秒"


def _format_epoch(current: int, total_epochs: int) -> str:
    if total_epochs > 0:
        return f"{current}/{total_epochs}"
    return str(current)


def metrics_from_anima_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    total_steps = 0
    total_epochs = 0
    loss_points: list[dict[str, float | int]] = []
    last_ts = 0.0
    last_step = 0

    for event in events:
        kind = event.get("ev") or event.get("event")
        ts = float(event.get("ts") or 0)
        if ts > 0:
            last_ts = ts

        if kind == "run_start":
            total_steps = int(event.get("total_steps") or total_steps or 0)
            total_epochs = int(event.get("total_epochs") or total_epochs or 0)
            metrics["total_steps"] = total_steps
            metrics["started"] = True
        elif kind == "step":
            step = int(event.get("global_step") or event.get("step") or 0)
            total = int(event.get("total_steps") or total_steps or 0)
            loss = _pick_loss(event)
            last_step = step
            metrics.update({
                "step": step,
                "total_steps": total,
                "percent": round(step * 100 / total, 2) if total else 0,
            })
            epoch_raw = event.get("epoch")
            if epoch_raw is not None:
                try:
                    metrics["epoch"] = _format_epoch(int(epoch_raw), total_epochs)
                except (TypeError, ValueError):
                    pass
            if loss is not None:
                try:
                    loss_float = float(loss)
                    metrics["loss"] = f"{loss_float:.4g}"
                    loss_points.append({"step": step, "loss": loss_float})
                except (TypeError, ValueError):
                    metrics["loss"] = str(loss)
        elif kind == "val":
            if "cmmd" in event:
                metrics["cmmd"] = event.get("cmmd")
            epoch_raw = event.get("epoch")
            if epoch_raw is not None and total_epochs > 0:
                try:
                    metrics["epoch"] = _format_epoch(int(epoch_raw), total_epochs)
                except (TypeError, ValueError):
                    pass
        elif kind == "ckpt":
            metrics["last_checkpoint"] = event.get("path")
        elif kind == "run_end":
            metrics["completed"] = event.get("status") == "ok"
            metrics["run_status"] = event.get("status")
            metrics["step"] = int(event.get("final_step") or metrics.get("step") or 0)
            if event.get("error"):
                metrics["has_error"] = True
                metrics["strong_error"] = event.get("error")

    if last_ts > 0:
        metrics["elapsed"] = _format_seconds(last_ts)
        if last_step > 0 and total_steps > last_step:
            rate = last_ts / last_step
            metrics["eta"] = _format_seconds((total_steps - last_step) * rate)

    if loss_points:
        metrics["loss_points"] = loss_points[-240:]
    return metrics


def merge_anima_training_metrics(
    stdout_metrics: dict[str, Any],
    anima_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Merge stdout-parsed Kohya/tqdm metrics with anima progress.jsonl metrics."""
    if not anima_metrics:
        return dict(stdout_metrics)

    merged = dict(stdout_metrics)
    jsonl_step = anima_metrics.get("step")
    stdout_step = merged.get("step")

    jsonl_has_progress = isinstance(jsonl_step, int) and jsonl_step > 0
    stdout_has_progress = isinstance(stdout_step, int) and stdout_step > 0
    prefer_jsonl_step = jsonl_has_progress and (
        not stdout_has_progress or jsonl_step >= stdout_step
    )

    progress_keys = ("step", "total_steps", "percent")
    for key in progress_keys:
        if prefer_jsonl_step and key in anima_metrics:
            merged[key] = anima_metrics[key]
        elif key not in merged and key in anima_metrics:
            merged[key] = anima_metrics[key]

    fill_keys = (
        "loss",
        "loss_points",
        "epoch",
        "elapsed",
        "eta",
        "cmmd",
        "last_checkpoint",
        "completed",
        "run_status",
        "started",
        "progress_source",
    )
    for key in fill_keys:
        value = anima_metrics.get(key)
        if value in (None, ""):
            continue
        if key == "eta" and str(merged.get("eta", "")).strip() not in ("", "?", "-"):
            continue
        if key in merged and merged.get(key) not in (None, "", "-", "?"):
            if key != "loss":
                continue
        merged[key] = value

    if anima_metrics.get("progress_source"):
        merged["progress_source"] = anima_metrics["progress_source"]
    return merged


def fallback_metrics_from_stdout(lines: list[str]) -> dict[str, Any]:
    text = "\n".join(lines[-1000:])
    matches = list(re.finditer(
        r"steps:\s*\d+%\|.*?\|\s*(?P<step>\d+)\s*/\s*(?P<total>\d+)"
        r".*?(?:loss|avr_loss|train_loss|loss/average|loss/current)[=:]\s*(?P<loss>[0-9.eE+-]+)",
        text,
    ))
    if not matches:
        return {}
    m = matches[-1]
    step = int(m.group("step"))
    total = int(m.group("total"))
    return {
        "step": step,
        "total_steps": total,
        "percent": round(step * 100 / total, 2) if total else 0,
        "loss": float(m.group("loss")),
    }

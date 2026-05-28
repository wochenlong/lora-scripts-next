from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any


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


def metrics_from_anima_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    total_steps = 0
    loss_points: list[dict[str, float | int]] = []
    for event in events:
        kind = event.get("ev") or event.get("event")
        if kind == "run_start":
            total_steps = int(event.get("total_steps") or total_steps or 0)
            metrics["total_steps"] = total_steps
            metrics["started"] = True
        elif kind == "step":
            step = int(event.get("global_step") or event.get("step") or 0)
            total = int(event.get("total_steps") or total_steps or 0)
            loss = event.get("loss") or event.get("train_loss")
            metrics.update({
                "step": step,
                "total_steps": total,
                "percent": round(step * 100 / total, 2) if total else 0,
            })
            if loss is not None:
                try:
                    loss_float = float(loss)
                    metrics["loss"] = str(loss)
                    loss_points.append({"step": step, "loss": loss_float})
                except (TypeError, ValueError):
                    metrics["loss"] = loss
        elif kind == "val":
            if "cmmd" in event:
                metrics["cmmd"] = event.get("cmmd")
        elif kind == "ckpt":
            metrics["last_checkpoint"] = event.get("path")
        elif kind == "run_end":
            metrics["completed"] = event.get("status") == "ok"
            metrics["run_status"] = event.get("status")
            metrics["step"] = int(event.get("final_step") or metrics.get("step") or 0)
            if event.get("error"):
                metrics["has_error"] = True
                metrics["strong_error"] = event.get("error")
    if loss_points:
        metrics["loss_points"] = loss_points[-240:]
    return metrics


def fallback_metrics_from_stdout(lines: list[str]) -> dict[str, Any]:
    text = "\n".join(lines[-1000:])
    matches = list(re.finditer(
        r"steps:\s*\d+%\|.*?\|\s*(?P<step>\d+)\s*/\s*(?P<total>\d+).*?(?:loss|avr_loss|train_loss)[=:]\s*(?P<loss>[0-9.eE+-]+)",
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

"""Best-effort parser for kogine/KohakuMoss step logs."""
import json
import math
import re
from pathlib import Path

STEP_RE = re.compile(r"\bstep\s+(\d+)\b", re.IGNORECASE)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def read_progress(lines, metadata):
    total = int(metadata.get("total_steps") or 0)
    for line in reversed(lines):
        match = STEP_RE.search(ANSI_RE.sub("", line))
        if not match:
            continue
        current = int(match.group(1))
        return {
            "step": current,
            "total_steps": total,
            "percent": min(100, int(current * 100 / total)) if total else 0,
        }
    return {}


def read_loss(metadata):
    """Kohaku's console logger writes JSONL, not TensorBoard events."""
    output = metadata.get("output_dir")
    if not output:
        return {}
    try:
        lines = (Path(output) / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    series = {}
    since = metadata.get("started_at") or metadata.get("created_at") or 0
    until = metadata.get("finished_at") or float("inf")
    for line in lines:
        try:
            row = json.loads(line)
            if not since - 1 <= row["time"] <= until + 5:
                continue
            for key, tag in (("loss", "loss/current"), ("lr", "lr/unet")):
                value = float(row[key])
                if math.isfinite(value):
                    series.setdefault(tag, []).append({"step": int(row["step"]), "value": value})
        except (ValueError, KeyError, TypeError):
            continue  # A live writer may not have finished its last JSONL row.
    return series

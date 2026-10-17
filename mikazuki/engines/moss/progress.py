"""Pinned upstream stdout format; synthetic tests only, not GPU-observed."""
import re

PROGRESS = re.compile(r"^\s*progress (\d+)/(\d+) epoch (\d+)/(\d+) loss ([\d.eE+-]+) eta (\d+:\d{2}:\d{2})\s*$")


def read_progress(lines, metadata):
    if metadata.get("kind") == "moss_install":
        return {}
    for line in reversed(lines):
        match = PROGRESS.match(line)
        if match:
            step, total, epoch, epochs = (int(match[i]) for i in range(1, 5))
            return {"step": step, "total_steps": total, "epoch": epoch, "total_epochs": epochs,
                    "percent": min(100, int(100 * step / total)) if total else 0,
                    "loss": float(match[5]), "eta": match[6]}
    return {}

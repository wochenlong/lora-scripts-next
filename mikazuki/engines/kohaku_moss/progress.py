"""Best-effort parser for kogine/KohakuMoss step logs."""
import re

STEP_RE = re.compile(r"(?:step|steps?)\s*[:=/ ]\s*(\d+)(?:\s*/\s*(\d+))?", re.IGNORECASE)


def read_progress(lines, metadata):
    total = int(metadata.get("total_steps") or 0)
    for line in reversed(lines):
        match = STEP_RE.search(line)
        if not match:
            continue
        current = int(match.group(1))
        observed_total = int(match.group(2) or total or 0)
        return {
            "current": current,
            "total": observed_total,
            "percent": int(current * 100 / observed_total) if observed_total else 0,
        }
    return None

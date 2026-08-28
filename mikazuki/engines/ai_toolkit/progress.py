"""ai-toolkit stdout progress parsing.

The training bar is a ToolkitProgressBar (tqdm) whose desc is the job name
(= config.config.name = metadata output_name). Latent-caching and sampling
bars carry different descs, so the job name is the anchor that keeps those
bars from being mistaken for training progress.
"""

from __future__ import annotations

import re


def parse_progress(log_lines: list[str], job_name: str) -> dict:
    job_name = (job_name or "").strip()
    if not job_name:
        return {}
    bar_re = re.compile(
        re.escape(job_name) + r"\s*:\s*(\d+)%\|[^|]*\|\s*(\d+)\s*/\s*(\d+)\s*\[([^\]]*)\]"
    )
    fragments: list[str] = []
    for line in log_lines[-400:]:
        fragments.extend(line.replace("\r", "\n").split("\n"))
    for line in reversed(fragments):
        match = bar_re.search(line)
        if not match:
            continue
        step = int(match.group(2))
        total = int(match.group(3))
        progress: dict = {
            "percent": int(match.group(1)),
            "step": step,
            "total_steps": total,
        }
        bracket = match.group(4)
        time_match = re.search(r"([^<,\]]+)<\s*([^,>\]]+)", bracket)
        if time_match:
            elapsed = time_match.group(1).strip()
            eta = time_match.group(2).strip()
            if elapsed:
                progress["elapsed"] = elapsed
            if eta not in ("", "?", "-"):
                progress["eta"] = eta
        loss_match = re.search(r"loss:\s*([0-9.eE+-]+)", bracket)
        if loss_match:
            try:
                progress["loss"] = float(loss_match.group(1))
            except ValueError:
                pass
        return progress
    return {}

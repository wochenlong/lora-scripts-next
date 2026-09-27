"""Use upstream CSV global steps instead of mistaking download tqdm for training."""
import csv
import json
from pathlib import Path


def read_progress(lines, metadata):
    if metadata.get("kind") == "diffsynth_install":
        return {}
    path = Path(metadata["output_dir"]) / "loss.csv"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        return {}
    row = rows[-1]
    step = int(row["step"])
    total = metadata["total_steps"]
    phase_path = path.parent / "phase.json"
    phase = json.loads(phase_path.read_text(encoding="utf-8")) if phase_path.exists() else {}
    return {**phase, "step": step, "total_steps": total, "percent": min(100, int(step * 100 / total)), "loss": float(row["value"])}

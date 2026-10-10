"""Keep concurrently submitted runs from sharing one output_name (#357).

Two runs with the same output_name write into the same output directory and
overwrite each other's checkpoints, loss events and previews. There was no
uniqueness check anywhere in the submit chain, so a name colliding with an
active task or an existing output directory is renamed automatically with a
``-DDHHMMSS-N`` suffix (N cycles 0-9) instead of being rejected.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import uuid


def _active_output_names(tm) -> set[str]:
    from mikazuki.tasks import TaskStatus

    terminal = {TaskStatus.FINISHED, TaskStatus.FAILED, TaskStatus.TERMINATED}
    names: set[str] = set()
    for task in tm.tasks.values():
        if task.status in terminal:
            continue
        name = str(task.metadata.get("output_name") or "").strip()
        if name:
            names.add(name)
    return names


from datetime import datetime
from pathlib import Path
import re
import sys
import uuid


def _artifact_pattern(name: str) -> re.Pattern:
    """Match any artifact an engine may write for this output_name.

    Layouts seen across engines (Kohya/sd-scripts, musubi, DiffSynth):
    - ``<name>`` directory or exact file
    - ``<name>.safetensors`` (final checkpoint)
    - ``<name>-000001.safetensors`` / ``<name>-step00001000.safetensors``
      (epoch/step checkpoints)
    - ``<name>-000001-state`` (optimizer state directory)
    Suffixes like ``<name>-v2`` are NOT artifacts of this run and must not
    force a rename.
    """
    return re.compile(rf"^{re.escape(name)}(?:\..+|-\d+(?:\..+|-state.*)?|-step\d+(?:\..+)?)?$")


def _output_artifacts_exist(output_dir: str, name: str) -> bool:
    """True when <output_dir> already holds artifacts for this output_name."""
    if not output_dir:
        return False
    # Windows filesystems are case-insensitive: submitting 'Lora' next to an
    # existing 'lora.safetensors' would collide at write time there.
    if sys.platform == "win32":
        pattern = _artifact_pattern(name.lower())
        probe = lambda entry_name: entry_name.lower()
    else:
        pattern = _artifact_pattern(name)
        probe = lambda entry_name: entry_name
    try:
        for entry in Path(output_dir).iterdir():
            if pattern.match(probe(entry.name)):
                return True
    except OSError:
        return False
    return False


def ensure_unique_output_name(config: dict, tm, now: datetime | None = None) -> str | None:
    """Rename ``config["output_name"]`` on collision; return the original name.

    Collision sources: active/queued compute tasks and existing artifacts
    under ``<output_dir>`` (directory or ``<name>.*`` files). Returns None
    when no rename was needed.
    """
    name = str(config.get("output_name") or "").strip()
    if not name:
        return None
    output_dir = str(config.get("output_dir") or "").strip()
    stamp = (now or datetime.now()).strftime("%d%H%M%S")
    active = _active_output_names(tm)

    def conflicts(candidate: str) -> bool:
        if candidate in active:
            return True
        return _output_artifacts_exist(output_dir, candidate)

    if not conflicts(name):
        return None
    for digit in range(10):
        candidate = f"{name}-{stamp}-{digit}"
        if not conflicts(candidate):
            config["output_name"] = candidate
            return name
    fallback = f"{name}-{stamp}-{uuid.uuid4().hex[:4]}"
    config["output_name"] = fallback
    return name

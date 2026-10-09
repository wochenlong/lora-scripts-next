from pathlib import Path
import os
from datetime import datetime, timezone

from mikazuki.datasets.root import normalize_path


def list_datasets(root: Path) -> list[dict]:
    if not root.is_dir():
        return []
    entries = [p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")]
    entries.sort(key=lambda p: p.name.lower())
    result = []
    for path in entries:
        stat = path.stat()
        # Unix ctime is metadata-change time, not directory creation time.
        created = getattr(stat, "st_birthtime", stat.st_ctime if os.name == "nt" else None)
        result.append({
            "name": path.name,
            "path": normalize_path(path),
            "created_at": datetime.fromtimestamp(created, timezone.utc).isoformat() if created is not None else None,
            "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        })
    return result

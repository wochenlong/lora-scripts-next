from pathlib import Path

from mikazuki.datasets.root import normalize_path


def list_datasets(root: Path) -> list[dict]:
    if not root.is_dir():
        return []
    entries = [p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")]
    entries.sort(key=lambda p: p.name.lower())
    return [{"name": p.name, "path": normalize_path(p)} for p in entries]

from pathlib import Path, PureWindowsPath

from fastapi import HTTPException

from mikazuki.dataset_editor import IMAGE_EXTENSIONS
from mikazuki.datasets.root import normalize_path


def dataset_contents(dataset_dir: Path, raw_path: str) -> dict:
    relative = raw_path.replace("\\", "/")
    parts = [part for part in relative.split("/") if part not in ("", ".")]
    if (
        relative.startswith("/")
        or PureWindowsPath(relative).drive
        or "\x00" in relative
        or any(part.startswith(".") or ":" in part for part in parts)
    ):
        raise HTTPException(status_code=400, detail="invalid dataset directory path")
    directory = dataset_dir.joinpath(*parts).resolve()
    try:
        resolved_relative = directory.relative_to(dataset_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes dataset") from exc
    if any(part.startswith(".") for part in resolved_relative.parts):
        raise HTTPException(status_code=400, detail="internal dataset directory")
    if not directory.is_dir():
        raise HTTPException(status_code=404, detail="directory not found")

    entries = []
    for entry in directory.iterdir():
        if entry.name.startswith(".") or entry.is_symlink():
            continue
        try:
            resolved = entry.resolve().relative_to(dataset_dir)
        except (ValueError, OSError):
            continue
        if any(part.startswith(".") for part in resolved.parts):
            continue
        if entry.is_dir():
            kind = "directory"
        elif entry.is_file():
            kind = "image" if entry.suffix.lower() in IMAGE_EXTENSIONS else "file"
        else:
            continue
        entries.append({"name": entry.name, "path": entry.relative_to(dataset_dir).as_posix(), "kind": kind})
    entries.sort(key=lambda entry: (entry["kind"] != "directory", entry["name"].lower(), entry["name"]))
    return {
        "name": dataset_dir.name,
        "path": normalize_path(directory),
        "relative_path": resolved_relative.as_posix() if resolved_relative.parts else "",
        "entries": entries,
    }

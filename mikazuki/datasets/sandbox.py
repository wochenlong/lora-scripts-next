from pathlib import Path, PureWindowsPath

from fastapi import HTTPException


def validate_dataset_name(name: str) -> str:
    stripped = name.strip()
    if not stripped or stripped in (".", "..") or stripped.startswith("."):
        raise HTTPException(status_code=400, detail="invalid dataset name")
    if "/" in stripped or "\\" in stripped:
        raise HTTPException(status_code=400, detail="invalid dataset name")
    return stripped


def resolve_dataset_dir(root: Path, name: str) -> Path:
    valid_name = validate_dataset_name(name)
    candidate = (root / valid_name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="dataset path is outside datasets root") from exc
    return candidate


def resolve_direct_dataset_dir(root: Path, name: str) -> Path:
    valid_name = validate_dataset_name(name)
    if (
        any(char in valid_name for char in '<>:"|?*')
        or any(ord(char) < 32 for char in valid_name)
        or valid_name.endswith(".")
        or PureWindowsPath(valid_name).is_reserved()
    ):
        raise HTTPException(status_code=400, detail="invalid dataset name")
    candidate = root / valid_name
    resolved = resolve_dataset_dir(root, valid_name)
    if candidate.is_symlink() or resolved != candidate:
        raise HTTPException(status_code=400, detail="dataset directory aliases are not supported")
    return resolved

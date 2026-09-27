from pathlib import Path

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

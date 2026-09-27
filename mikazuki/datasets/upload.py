from __future__ import annotations

import errno
import os
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from mikazuki.dataset_editor import IMAGE_EXTENSIONS

MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_BATCH_BYTES = 5 * 1024 * 1024 * 1024
MIN_FREE_BYTES = 512 * 1024 * 1024
CAPTION_EXTENSION = ".txt"
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | {CAPTION_EXTENSION}
_CHUNK = 1024 * 1024


def staging_root(datasets_root: Path) -> Path:
    return datasets_root / ".upload-tmp"


def sanitize_relative_path(raw: str) -> str:
    rel = (raw or "").strip().replace("\\", "/")
    if not rel or rel.startswith("/") or rel.startswith("."):
        raise ValueError(f"invalid upload path: {raw!r}")
    parts = [part for part in rel.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." or part.startswith(".") for part in parts):
        raise ValueError(f"invalid upload path: {raw!r}")
    name = parts[-1]
    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"unsupported file type: {name}")
    return "/".join(parts)


def resolve_upload_target(dataset_dir: Path, rel: str) -> Path:
    target = (dataset_dir / rel).resolve()
    try:
        target.relative_to(dataset_dir)
    except ValueError as exc:
        raise ValueError(f"upload path escapes dataset: {rel}") from exc
    return target


async def stage_upload(upload: UploadFile, staging_dir: Path, rel: str) -> tuple[Path, int]:
    staged = staging_dir / rel
    staged.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with staged.open("wb") as out:
            while True:
                chunk = await upload.read(_CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_FILE_BYTES:
                    raise ValueError(f"file exceeds {MAX_FILE_BYTES // (1024 * 1024)}MB limit")
                out.write(chunk)
    except OSError as exc:
        staged.unlink(missing_ok=True)
        if exc.errno == errno.ENOSPC:
            raise HTTPException(status_code=507, detail="insufficient disk space while receiving upload") from exc
        raise
    except Exception:
        staged.unlink(missing_ok=True)
        raise
    return staged, written


def ensure_staging_headroom(staging_dir: Path) -> None:
    if shutil.disk_usage(staging_dir).free < MIN_FREE_BYTES:
        raise HTTPException(status_code=507, detail="insufficient disk space while receiving upload")


def validate_readable(staged: Path) -> None:
    if staged.suffix.lower() in IMAGE_EXTENSIONS:
        try:
            with Image.open(staged) as image:
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("image is not readable") from exc
    else:
        staged.read_text(encoding="utf-8")


def ensure_capacity(dataset_dir: Path, moves: list[tuple[Path, Path]]) -> None:
    if not moves:
        return
    free = shutil.disk_usage(dataset_dir).free
    required = 0
    for staged, target in moves:
        staged_size = staged.stat().st_size
        try:
            same_device = staged.stat().st_dev == dataset_dir.stat().st_dev
        except OSError:
            same_device = False
        reclaimed = target.stat().st_size if target.is_file() else 0
        needed = staged_size - reclaimed
        if same_device:
            needed -= staged_size
        if needed > 0:
            required += needed
    if required > free:
        raise HTTPException(status_code=507, detail="insufficient disk space for upload")


def move_staged(staged: Path, target: Path, overwrite: bool) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        shutil.move(str(staged), str(target))
        return True
    try:
        os.link(staged, target)
    except FileExistsError:
        staged.unlink(missing_ok=True)
        return False
    except OSError:
        try:
            with staged.open("rb") as src, target.open("xb") as out:
                shutil.copyfileobj(src, out)
        except FileExistsError:
            staged.unlink(missing_ok=True)
            return False
    staged.unlink(missing_ok=True)
    return True


def cleanup_staging(staging_dir: Path) -> None:
    shutil.rmtree(staging_dir, ignore_errors=True)


def new_staging_dir(datasets_root: Path) -> Path:
    staging = staging_root(datasets_root) / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=True)
    return staging


def relative_of(dataset_dir: Path, path: Path) -> str:
    return str(path.relative_to(dataset_dir)).replace("\\", "/")

"""Server-side filesystem listing for the in-browser path picker (#244)."""

from __future__ import annotations

import os
import re
import string
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

# Linux virtual FS — never useful for training assets.
_LINUX_DENY_PREFIXES = (
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/snap",
)

_MODEL_NAME_RE = re.compile(r"\.(safetensors|ckpt|pt)$", re.IGNORECASE)


def gui_picker_available() -> bool:
    """True when a native tkinter dialog can plausibly show on this host."""
    try:
        from mikazuki.utils.tk_window import tkinter_available
    except Exception:
        return False
    if not tkinter_available():
        return False
    if sys.platform.startswith("win"):
        return True
    # Linux / macOS need a display for Tk.
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _project_cwd() -> Path:
    return Path.cwd().resolve()


def default_roots() -> list[dict[str, str]]:
    """Shortcut roots shown in the picker sidebar."""
    cwd = _project_cwd()
    candidates: list[tuple[str, Path]] = [
        ("cwd", cwd),
        ("sd-models", cwd / "sd-models"),
        ("train", cwd / "train"),
        ("output", cwd / "output"),
        ("logs", cwd / "logs"),
        ("tagger-models", cwd / "tagger-models"),
    ]
    if sys.platform.startswith("win"):
        for letter in string.ascii_uppercase:
            root = Path(f"{letter}:/")
            if root.exists():
                candidates.append((f"drive-{letter}", root))
    else:
        for label, path in (
            ("root", Path("/")),
            ("home", Path.home()),
            ("data", Path("/data")),
            ("mnt", Path("/mnt")),
            ("workspace", Path("/workspace")),
        ):
            candidates.append((label, path))

    seen: set[str] = set()
    roots: list[dict[str, str]] = []
    for label, path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if not resolved.exists() or not resolved.is_dir():
            continue
        key = str(resolved).replace("\\", "/")
        if key in seen:
            continue
        seen.add(key)
        roots.append({"id": label, "label": label, "path": key})
    return roots


def _is_denied(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return True
    text = str(resolved).replace("\\", "/")
    if sys.platform.startswith("win"):
        lower = text.lower()
        if lower.startswith("c:/windows") or lower.startswith("c:/program files"):
            return True
        return False
    for prefix in _LINUX_DENY_PREFIXES:
        if text == prefix or text.startswith(prefix + "/"):
            return True
    return False


def resolve_list_path(raw: Optional[str]) -> Path:
    cwd = _project_cwd()
    if not raw or not str(raw).strip():
        return cwd
    text = str(raw).strip().replace("\\", "/")
    path = Path(text)
    if not path.is_absolute():
        path = cwd / path
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise ValueError(f"无法解析路径: {text}") from exc
    if _is_denied(resolved):
        raise PermissionError(f"不允许浏览该路径: {resolved}")
    if not resolved.exists():
        # Fall back to nearest existing parent for sticky navigation.
        parent = resolved
        while parent != parent.parent and not parent.exists():
            parent = parent.parent
        if parent.exists() and parent.is_dir() and not _is_denied(parent):
            return parent
        raise FileNotFoundError(f"路径不存在: {resolved}")
    if not resolved.is_dir():
        if resolved.parent.exists():
            return resolved.parent.resolve()
        raise NotADirectoryError(f"不是目录: {resolved}")
    return resolved


def _match_filter(name: str, mode: str, name_filter: Optional[str]) -> bool:
    if mode == "folder":
        return True
    if not name_filter or name_filter in ("*", "*.*"):
        return _MODEL_NAME_RE.search(name) is not None
    # Accept regex or simple extension list like "*.safetensors;*.ckpt;*.pt"
    if "(" in name_filter:
        try:
            return re.search(name_filter, name, re.IGNORECASE) is not None
        except re.error:
            pass
    parts = [p.strip() for p in re.split(r"[;,]", name_filter) if p.strip()]
    if not parts:
        return _MODEL_NAME_RE.search(name) is not None
    for part in parts:
        if part.startswith("*."):
            if name.lower().endswith(part[1:].lower()):
                return True
        elif part.startswith("."):
            if name.lower().endswith(part.lower()):
                return True
        elif name.lower().endswith(part.lower()):
            return True
    return False


def list_directory(
    raw_path: Optional[str] = None,
    *,
    mode: str = "folder",
    name_filter: Optional[str] = None,
) -> dict[str, Any]:
    """List one directory for the web path picker.

    mode:
      - folder: directories only (user confirms current path)
      - file: directories + filtered files
    """
    if mode not in ("folder", "file"):
        raise ValueError(f"不支持的 mode: {mode}")

    current = resolve_list_path(raw_path)
    parent = current.parent if current.parent != current else None
    if parent is not None and _is_denied(parent):
        parent = None

    entries: list[dict[str, Any]] = []
    try:
        children: Iterable[Path] = sorted(
            current.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
    except PermissionError as exc:
        raise PermissionError(f"没有权限读取: {current}") from exc
    except OSError as exc:
        raise OSError(f"无法读取目录: {current}") from exc

    for child in children:
        name = child.name
        if name in {".git", ".ipynb_checkpoints", ".DS_Store", "Thumbs.db"}:
            continue
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        if is_dir:
            if _is_denied(child):
                continue
            try:
                child_path = str(child.resolve()).replace("\\", "/")
            except OSError:
                child_path = str(child).replace("\\", "/")
            entries.append({"name": name, "path": child_path, "type": "dir"})
            continue
        if mode != "file":
            continue
        if not _match_filter(name, mode, name_filter):
            continue
        try:
            stat = child.stat()
            size_bytes = int(stat.st_size)
            mtime = int(stat.st_mtime)
            child_path = str(child.resolve()).replace("\\", "/")
        except OSError:
            continue
        entries.append(
            {
                "name": name,
                "path": child_path,
                "type": "file",
                "size_bytes": size_bytes,
                "mtime": mtime,
            }
        )

    return {
        "path": str(current).replace("\\", "/"),
        "parent": str(parent).replace("\\", "/") if parent is not None else None,
        "mode": mode,
        "entries": entries,
        "roots": default_roots(),
        "gui_picker": gui_picker_available(),
    }

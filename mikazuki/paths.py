"""Opt-in profile paths; callers keep their exact legacy path when unset.

The launcher keeps cwd at the selected source version. Shared preferences use
NEXT_TRAINER_DATA_ROOT; version-specific state additionally honors
NEXT_TRAINER_STATE_ROOT. Resolving a path never creates or migrates files.
"""

from __future__ import annotations

import os
from pathlib import Path


DATA_ROOT_ENV = "NEXT_TRAINER_DATA_ROOT"
STATE_ROOT_ENV = "NEXT_TRAINER_STATE_ROOT"


def _configured_root(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute directory path / 必须使用绝对目录路径")
    return path.resolve()


def data_path(
    relative: str | os.PathLike[str],
    *,
    legacy_base: str | os.PathLike[str] | None = None,
    state: bool = False,
) -> Path:
    """Resolve an application-owned path, preserving legacy behavior by default.

    ``state=True`` selects STATE_ROOT, then DATA_ROOT. Shared data selects only
    DATA_ROOT. Explicit per-feature overrides should be handled by the caller
    before using this helper. ``relative`` is a trusted application-owned name,
    not an API-supplied filesystem path.
    """
    relative = Path(relative)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ValueError("Application data path must be relative and cannot contain ..")
    root = (_configured_root(STATE_ROOT_ENV) if state else None) or _configured_root(DATA_ROOT_ENV)
    if root is not None:
        return root / relative
    return Path(legacy_base) / relative if legacy_base is not None else relative

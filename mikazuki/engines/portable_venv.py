"""Detect and repair extension venvs whose base interpreter moved.

Windows portable packages ship pre-built extension venvs whose ``pyvenv.cfg``
records the build machine's absolute interpreter path. After the package is
extracted somewhere else the venv launcher fails with ``No Python at ...``
even though the matching interpreter ships inside the package (``.python/``).

The helpers here rewrite ``pyvenv.cfg`` to the in-project interpreter, or
report the venv as broken so installers rebuild it. Repair only triggers when
the recorded home no longer resolves AND a matching in-project interpreter
exists, so venvs built by the user on their own machine are never touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable
import os
import sys
import tempfile


LogFn = Callable[[str], None]

REPAIR_OK = "ok"
REPAIR_RELOCATED = "relocated"
REPAIR_BROKEN = "broken"


def venv_cfg_path(venv_python: Path) -> Path:
    return venv_python.parent.parent / "pyvenv.cfg"


def read_venv_home(venv_python: Path) -> Path | None:
    cfg = venv_cfg_path(venv_python)
    if not cfg.is_file():
        return None
    for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip().lower() == "home":
            value = value.strip()
            return Path(value) if value else None
    return None


def venv_base_missing(venv_python: Path) -> bool:
    """True when the venv exists but its recorded base interpreter is gone."""
    if not venv_python.is_file():
        return False
    home = read_venv_home(venv_python)
    return home is not None and not home.is_dir()


def find_packaged_base_python(python_install_dir: Path, version: str) -> Path | None:
    """Locate a uv-installed interpreter of ``version`` under the project."""
    if not python_install_dir.is_dir():
        return None
    if sys.platform == "win32":
        patterns = [f"cpython-{version}.*-windows-*/python.exe"]
    else:
        patterns = [
            f"cpython-{version}.*-linux*/bin/python3",
            f"cpython-{version}.*-linux*/bin/python",
        ]
    for pattern in patterns:
        candidates = sorted(python_install_dir.glob(pattern), reverse=True)
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
    return None


def relocate_venv_home(venv_python: Path, base_python: Path) -> None:
    """Point pyvenv.cfg at ``base_python``; drop build-machine metadata."""
    cfg = venv_cfg_path(venv_python)
    original = cfg.read_text(encoding="utf-8", errors="replace")
    base_dir = base_python.parent
    lines: list[str] = []
    seen: set[str] = set()
    for line in original.splitlines():
        key, separator, _value = line.partition("=")
        name = key.strip().lower()
        if not separator:
            continue
        if name == "command":
            continue
        if name == "home":
            line = f"home = {base_dir}"
        elif name == "executable":
            line = f"executable = {base_python}"
        elif name == "include-system-site-packages":
            line = "include-system-site-packages = false"
        seen.add(name)
        lines.append(line)
    if "home" not in seen:
        lines.insert(0, f"home = {base_dir}")
    text = "\n".join(lines) + "\n"
    if text == original:
        return
    fd, staged_name = tempfile.mkstemp(dir=cfg.parent)
    staged = Path(staged_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(text.encode("utf-8"))
        os.replace(staged, cfg)
    finally:
        staged.unlink(missing_ok=True)


def repair_venv_base(
    venv_python: Path,
    python_install_dir: Path,
    version: str,
    log: LogFn | None = None,
) -> str:
    """Heal a venv whose base interpreter moved; returns ok/relocated/broken.

    A missing venv is the installer's normal create path, not a repair case.
    """
    if not venv_python.is_file():
        return REPAIR_OK
    if not venv_base_missing(venv_python):
        return REPAIR_OK
    base_python = find_packaged_base_python(python_install_dir, version)
    if base_python is None:
        return REPAIR_BROKEN
    stale_home = read_venv_home(venv_python)
    relocate_venv_home(venv_python, base_python)
    if log:
        log(f"[repair] venv 引用的基础 Python 已失效（{stale_home}），已迁移到 {base_python}")
    return REPAIR_RELOCATED

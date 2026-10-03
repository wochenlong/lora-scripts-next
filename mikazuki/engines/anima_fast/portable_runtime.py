"""Relocate only explicitly packaged Windows Fast environments."""

import json
import os
from pathlib import Path
import tempfile
import shutil


def rebuild_base(root: Path, base_python: Path) -> Path:
    """Explicit installer recovery; preserve venv packages and user data."""
    root = Path(root).resolve()
    target = root / ".python"
    for path in (target, root / ".venv", root / "portable-runtime.json"):
        if not path.resolve().is_relative_to(root):
            raise RuntimeError("Portable Fast runtime points outside its package")
    # Never follow existing junctions/symlinks while repairing a copied tree.
    for directory in (target, root / ".venv"):
        if directory.resolve() != directory.absolute():
            raise RuntimeError("Portable runtime contains a linked path")
        for path in directory.rglob("*"):
            if path.resolve() != path.absolute():
                raise RuntimeError("Portable runtime contains a linked path")
    shutil.copytree(
        Path(base_python).resolve().parent, target, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("site-packages", "__pycache__", "*.pyc", ".git"),
    )
    (root / "portable-runtime.json").write_text('{"version": 1}', encoding="utf-8")
    return target / "python.exe"


def repair(root: Path) -> None:
    root = Path(root).resolve()
    marker = root / "portable-runtime.json"
    if not marker.is_file():
        return
    if json.loads(marker.read_text(encoding="utf-8")) != {"version": 1}:
        raise RuntimeError("Unsupported portable Fast runtime marker")
    base = root / ".python"
    config = root / ".venv/pyvenv.cfg"
    for path in (base, config.parent, config):
        if not path.resolve().is_relative_to(root):
            raise RuntimeError("Portable Fast runtime points outside its package")
    if not (base / "python.exe").is_file():
        raise RuntimeError("Bundled base Python is missing; re-extract the Fast package")
    original = config.read_text(encoding="utf-8")
    values = {}
    for line in original.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    values.update(home=str(base), executable=str(base / "python.exe"))
    values["include-system-site-packages"] = "false"
    # Build-machine command metadata is not needed to run the environment.
    values.pop("command", None)
    text = "".join(f"{key} = {value}\n" for key, value in values.items())
    if text == original:
        return
    with tempfile.NamedTemporaryFile(dir=config.parent, delete=False) as stream:
        staged = Path(stream.name)
        stream.write(text.encode("utf-8"))
    try:
        os.replace(staged, config)
    finally:
        staged.unlink(missing_ok=True)

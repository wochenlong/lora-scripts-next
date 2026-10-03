"""Bundle the base interpreter belonging to a copied Windows Fast venv."""

import argparse
import json
from pathlib import Path
import runpy
import shutil
import subprocess


def bundle(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source.is_relative_to(destination):
        raise RuntimeError("Source and destination must be separate")
    python = source / ".venv/Scripts/python.exe"
    base = Path(subprocess.check_output(
        [str(python), "-I", "-c", "import sys; print(sys.base_prefix)"],
        text=True).strip()).resolve()
    if not (base / "python.exe").is_file():
        raise RuntimeError("Source base Python is missing")
    target = destination / ".python"
    if target.exists():
        raise RuntimeError("Bundled base destination already exists; use a fresh build")
    # Keep stdlib/DLLs, never inherit packages from a developer base interpreter.
    shutil.copytree(base, target, ignore=shutil.ignore_patterns(
        "site-packages", "__pycache__", "*.pyc", ".git"))
    (destination / "portable-runtime.json").write_text(
        json.dumps({"version": 1}), encoding="utf-8")
    module = Path(__file__).resolve().parents[2] / "mikazuki/engines/anima_fast/portable_runtime.py"
    runpy.run_path(str(module))["repair"](destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    bundle(args.source, args.destination)

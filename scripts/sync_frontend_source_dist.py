#!/usr/bin/env python3
"""Guarded sync from source-built frontend output to production frontend/dist.

The default mode is a dry run.  Use --apply only after source verification and
browser smoke have passed.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SOURCE_DIST = Path("build/frontend-source-dist")
TARGET_DIST = Path("frontend/dist")
# The classic tag editor entrypoint is source-owned and no longer depends on
# the legacy Gradio proxy or old VuePress chunks.
LEGACY_ISLAND_ENTRYPOINTS = ()
LEGACY_ISLAND_ASSETS = ()


def verify_source_dist(root: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "scripts/verify_frontend_source.py",
            "--root",
            str(root),
            "--require-built-output",
        ],
        cwd=root,
        check=True,
    )


def assert_expected_paths(root: Path, source: Path, target: Path) -> None:
    expected_source = (root / SOURCE_DIST).resolve()
    expected_target = (root / TARGET_DIST).resolve()
    if source.resolve() != expected_source:
        raise RuntimeError(f"refusing unexpected source path: {source}")
    if target.resolve() != expected_target:
        raise RuntimeError(f"refusing unexpected target path: {target}")
    if not (source / "index.html").is_file():
        raise RuntimeError(f"source dist is missing index.html: {source}")
    if not (source / "assets").is_dir():
        raise RuntimeError(f"source dist is missing assets/: {source}")


def backup_target(root: Path, target: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = root / "build" / f"frontend-dist-backup-{stamp}"
    if target.exists():
        shutil.copytree(target, backup)
    return backup


def collect_legacy_island(target: Path) -> dict[Path, bytes]:
    files: set[Path] = {Path(path) for path in LEGACY_ISLAND_ENTRYPOINTS}
    files.update(Path(path) for path in LEGACY_ISLAND_ASSETS)

    for entrypoint in LEGACY_ISLAND_ENTRYPOINTS:
        html_path = target / entrypoint
        if not html_path.is_file():
            continue
        html = html_path.read_text(encoding="utf-8")
        for match in re.finditer(r"""(?:href|src)=["'](/[^"'?#]+)""", html):
            relative_path = Path(match.group(1).lstrip("/"))
            if relative_path.parts[:1] == ("assets",) or relative_path.as_posix() == "favicon.ico":
                files.add(relative_path)

    legacy_files: dict[Path, bytes] = {}
    for relative_path in files:
        source = target / relative_path
        if source.is_file():
            legacy_files[relative_path] = source.read_bytes()
    return legacy_files


def restore_legacy_island(target: Path, legacy_files: dict[Path, bytes]) -> None:
    for relative_path, content in legacy_files.items():
        destination = target / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


def sync_dist(source: Path, target: Path, *, backup: bool, root: Path) -> None:
    legacy_files = collect_legacy_island(target) if target.exists() else {}
    backup_path = backup_target(root, target) if backup else None
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    restore_legacy_island(target, legacy_files)
    if backup_path:
        print(f"backup written: {backup_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    source = root / SOURCE_DIST
    target = root / TARGET_DIST
    assert_expected_paths(root, source, target)
    verify_source_dist(root)

    if not args.apply:
        print(f"source dist sync plan OK: {SOURCE_DIST.as_posix()} -> {TARGET_DIST.as_posix()}")
        print("dry run only; pass --apply to replace frontend/dist")
        return 0

    sync_dist(source, target, backup=args.backup, root=root)
    print(f"synced {SOURCE_DIST.as_posix()} -> {TARGET_DIST.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

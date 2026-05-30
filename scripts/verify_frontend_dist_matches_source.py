#!/usr/bin/env python3
"""Verify production frontend/dist matches the source-built dist exactly."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


SOURCE_DIST = Path("build/frontend-source-dist")
TARGET_DIST = Path("frontend/dist")


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_files(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise RuntimeError(f"missing directory: {root}")
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[path.relative_to(root).as_posix()] = file_digest(path)
    return files


def main() -> int:
    source = collect_files(SOURCE_DIST)
    target = collect_files(TARGET_DIST)
    missing = sorted(set(source) - set(target))
    extra = sorted(set(target) - set(source))
    changed = sorted(path for path in set(source) & set(target) if source[path] != target[path])

    if missing or extra or changed:
        print("frontend dist does not match source build", file=sys.stderr)
        if missing:
            print(f"missing from frontend/dist: {missing[:20]}", file=sys.stderr)
        if extra:
            print(f"extra in frontend/dist: {extra[:20]}", file=sys.stderr)
        if changed:
            print(f"changed files: {changed[:20]}", file=sys.stderr)
        return 1

    print(f"frontend dist matches source build ({len(source)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

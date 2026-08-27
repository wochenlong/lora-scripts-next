"""Vendor source bundle: offline distribution of pinned upstream sources.

``vendor/vendor-bundle.zip`` (or ``.tar.gz`` / ``.tgz`` / ``.tar``) holds
top-level source dirs (``musubi-tuner/``, ``anima_lora/``, ...) — each the
``git archive`` content of the engine's pinned commit plus a
``.source_commit`` marker file. When an engine's vendor dir is missing, the
bundle is extracted into ``vendor/`` once, so source resolution never touches
the network. Packing instructions: ``mikazuki/engines/VENDOR_BUNDLE.md``.
"""

from __future__ import annotations

import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path

BUNDLE_NAMES = (
    "vendor-bundle.zip",
    "vendor-bundle.tar.gz",
    "vendor-bundle.tgz",
    "vendor-bundle.tar",
)

_EXTRACT_MARKER = ".vendor_bundle_extracted"


def find_vendor_bundle(project_root: Path) -> Path | None:
    vendor = project_root / "vendor"
    for name in BUNDLE_NAMES:
        candidate = vendor / name
        if candidate.is_file():
            return candidate
    return None


def snapshot_commit(source_root: Path) -> str | None:
    marker = source_root / ".source_commit"
    if not marker.is_file():
        return None
    return marker.read_text(encoding="utf-8").strip() or None


def snapshot_matches(source_root: Path, commit: str) -> bool:
    """True when source_root is an exact snapshot of commit.

    The recorded marker must be a full 40-hex SHA (the bundle contract); the
    requested commit may be an unambiguous prefix of it.
    """
    recorded = snapshot_commit(source_root)
    if not recorded or not commit:
        return False
    recorded = recorded.lower()
    if len(recorded) != 40 or any(c not in "0123456789abcdef" for c in recorded):
        return False
    return recorded.startswith(commit.strip().lower())


def _check_within(base: Path, name: str) -> None:
    destination = (base / name).resolve()
    destination.relative_to(base.resolve())


def extract_vendor_bundle(bundle: Path, vendor_dir: Path, log: Callable[[str], None] | None = None) -> None:
    vendor_dir.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(bundle):
        with zipfile.ZipFile(bundle) as zf:
            for info in zf.infolist():
                _check_within(vendor_dir, info.filename)
            zf.extractall(vendor_dir)
    else:
        with tarfile.open(bundle) as tf:
            for member in tf.getmembers():
                _check_within(vendor_dir, member.name)
            try:
                tf.extractall(vendor_dir, filter="data")
            except TypeError:  # Python < 3.11.4 has no filter parameter
                tf.extractall(vendor_dir)
    marker = vendor_dir / _EXTRACT_MARKER
    marker.write_text(f"{bundle.name}\n{bundle.stat().st_size}\n", encoding="utf-8")


def _bundle_already_extracted(bundle: Path, vendor_dir: Path) -> bool:
    marker = vendor_dir / _EXTRACT_MARKER
    if not marker.is_file():
        return False
    try:
        name, size = marker.read_text(encoding="utf-8").splitlines()[:2]
    except ValueError:
        return False
    return name == bundle.name and int(size) == bundle.stat().st_size


def ensure_vendor_source(
    project_root: Path,
    dirname: str,
    log: Callable[[str], None] | None = None,
) -> Path | None:
    """Return ``vendor/<dirname>``, extracting the vendor bundle once if needed."""
    vendor_dir = project_root / "vendor"
    target = vendor_dir / dirname
    if target.is_dir():
        return target.resolve()
    bundle = find_vendor_bundle(project_root)
    if bundle is None or _bundle_already_extracted(bundle, vendor_dir):
        return None
    if log:
        log(f"[vendor] extracting {bundle.name} into vendor/")
    extract_vendor_bundle(bundle, vendor_dir, log=log)
    if target.is_dir():
        return target.resolve()
    if log:
        log(f"[vendor] bundle does not contain {dirname}/")
    return None

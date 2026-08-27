"""Vendor source bundle: offline distribution of pinned upstream sources.

``vendor/vendor-bundle.zip`` (or ``.tar.gz`` / ``.tgz`` / ``.tar``) holds
top-level source dirs (``musubi-tuner/``, ``anima_lora/``, ...) — each the
``git archive`` content of the engine's pinned commit plus a
``.source_commit`` marker file. When an engine's vendor dir is missing, the
bundle is extracted into ``vendor/`` once, so source resolution never touches
the network. Packing instructions: ``mikazuki/engines/VENDOR_BUNDLE.md``.
"""

from __future__ import annotations

import hashlib
import shutil
import tarfile
import threading
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
_STAGING_DIR = ".vendor_bundle_staging"

# Serializes extraction inside this process; staging + atomic promotion keeps
# concurrent readers from ever seeing a half-extracted tree.
_EXTRACTION_LOCK = threading.Lock()


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


def _bundle_digest(bundle: Path) -> str:
    digest = hashlib.sha256()
    with bundle.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_vendor_bundle(bundle: Path, vendor_dir: Path, log: Callable[[str], None] | None = None) -> None:
    """Extract bundle into a staging dir, then promote entries atomically."""
    vendor_dir.mkdir(parents=True, exist_ok=True)
    staging = vendor_dir / _STAGING_DIR
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        if zipfile.is_zipfile(bundle):
            with zipfile.ZipFile(bundle) as zf:
                for info in zf.infolist():
                    _check_within(staging, info.filename)
                zf.extractall(staging)
        else:
            with tarfile.open(bundle) as tf:
                for member in tf.getmembers():
                    _check_within(staging, member.name)
                    if member.issym() or member.islnk():
                        # Link targets must also stay inside the staging dir.
                        target = ((staging / member.name).parent / member.linkname).resolve()
                        target.relative_to(staging.resolve())
                try:
                    tf.extractall(staging, filter="data")
                except TypeError:  # Python < 3.11.4 has no filter parameter
                    tf.extractall(staging)
        for entry in staging.iterdir():
            destination = vendor_dir / entry.name
            if destination.exists():
                continue
            entry.rename(destination)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    marker = vendor_dir / _EXTRACT_MARKER
    marker.write_text(f"{bundle.name}\n{_bundle_digest(bundle)}\n", encoding="utf-8")


def _bundle_already_extracted(bundle: Path, vendor_dir: Path) -> bool:
    marker = vendor_dir / _EXTRACT_MARKER
    if not marker.is_file():
        return False
    try:
        name, digest = marker.read_text(encoding="utf-8").splitlines()[:2]
    except ValueError:
        return False
    if name != bundle.name:
        return False
    return digest == _bundle_digest(bundle)


def ensure_vendor_source(
    project_root: Path,
    dirname: str,
    log: Callable[[str], None] | None = None,
) -> Path | None:
    """Return ``vendor/<dirname>``, extracting the vendor bundle once if needed.

    One-shot distribution contract: an existing vendor dir is never
    overwritten. Dirs we extracted ourselves are trusted as-is; manually
    placed dirs win over the bundle with a loud warning (DIY at your own
    risk). Upgrades go through github/gitee clones — a pin bump makes stale
    snapshots fail the .source_commit check and fall through to clone.
    """
    vendor_dir = project_root / "vendor"
    target = vendor_dir / dirname
    if target.is_dir():
        bundle = find_vendor_bundle(project_root)
        if bundle is not None and not _bundle_already_extracted(bundle, vendor_dir):
            message = (
                f"[vendor] {dirname} 已存在且非本 bundle 解压产物（或 bundle 已更换）；"
                "按一次性分发约定不覆盖。升级请走 GitHub/Gitee，"
                f"或手动删除 vendor/{dirname} 后重新安装（手动目录 DIY 场景仅告警）。"
            )
            if log:
                log(message)
            else:
                from mikazuki.log import log as _log

                _log.warning(message)
        return target.resolve()
    with _EXTRACTION_LOCK:
        # Re-check under the lock: another thread may have just promoted it.
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

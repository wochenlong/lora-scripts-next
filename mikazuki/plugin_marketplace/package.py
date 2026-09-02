from __future__ import annotations

import json
import os
import shutil
import stat
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from .models import MarketplaceEntry, PluginManifest


class PackageValidationError(ValueError):
    pass


def _raw_path(path: Path) -> Path:
    """Windows MAX_PATH guard for deep archive trees.

    Self-contained runtime packages (pi-web's vendored SDKs under
    node_modules) produce member paths beyond the 260-character Win32
    limit; the ``\\?\\`` raw prefix is the only supported way to reach
    them from Python.  No-op on other platforms.
    """
    if os.name != "nt":
        return path
    text = str(path)
    return Path(text) if text.startswith("\\\\?\\") else Path(f"\\\\?\\{text}")


def remove_tree(path: Path, *, ignore_errors: bool = False) -> None:
    """Recursive removal that works on trees deeper than MAX_PATH (Windows).

    Mirrors ``shutil.rmtree`` semantics (including ``ignore_errors``) but
    walks with raw-prefixed paths so deep ``node_modules`` trees are not
    silently left behind.
    """
    root = _raw_path(path)
    if not root.exists():
        return

    def _clear(entry: Path) -> None:
        try:
            if entry.is_dir() and not entry.is_symlink():
                entry.rmdir()
            else:
                entry.unlink()
        except OSError:
            if ignore_errors:
                return
            # Read-only artifacts (e.g. npm-staged files) block unlink on
            # Windows; one chmod retry before surfacing the failure.
            try:
                entry.chmod(0o700)
                if entry.is_dir() and not entry.is_symlink():
                    entry.rmdir()
                else:
                    entry.unlink()
            except OSError:
                if ignore_errors:
                    return
                raise

    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in list(filenames) + list(dirnames):
            _clear(Path(dirpath) / name)
    try:
        root.rmdir()
    except OSError:
        if ignore_errors:
            return
        raise


@dataclass(frozen=True)
class PackageLimits:
    # Upper bounds sized for self-contained runtime plugins (e.g. the
    # verbatim pi-web + pi coding-agent embed: ~291 MB zip, ~1.22 GB
    # unpacked, ~34.5k files) while still bounding pathological packages.
    max_package_bytes: int = 512 * 1024 * 1024
    max_unpacked_bytes: int = 2 * 1024 * 1024 * 1024
    max_files: int = 50_000


def _validate_member(name: str) -> PurePosixPath:
    if not name or "\\" in name or name.startswith(("/", "\\")):
        raise PackageValidationError(f"unsafe archive path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or any(":" in part for part in path.parts):
        raise PackageValidationError(f"unsafe archive path: {name!r}")
    return path


def inspect_package(package_path: Path, limits: PackageLimits) -> tuple[PluginManifest, list[zipfile.ZipInfo]]:
    if package_path.stat().st_size > limits.max_package_bytes:
        raise PackageValidationError("package size limit exceeded")
    try:
        archive = zipfile.ZipFile(package_path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise PackageValidationError("plugin package is not a valid ZIP archive") from exc
    with archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if len(members) > limits.max_files:
            raise PackageValidationError("archive file count limit exceeded")
        if sum(item.file_size for item in members) > limits.max_unpacked_bytes:
            raise PackageValidationError("archive unpacked size limit exceeded")
        names: dict[str, str] = {}
        for item in members:
            _validate_member(item.filename)
            folded = item.filename.casefold()
            if folded in names:
                raise PackageValidationError(f"duplicate archive path: {item.filename}")
            names[folded] = item.filename
            mode = (item.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode) or (item.external_attr & 0x400):
                raise PackageValidationError(f"links/reparse points are forbidden: {item.filename}")
        manifest_name = names.get("plugin.json")
        if manifest_name is None:
            raise PackageValidationError("plugin.json is missing")
        try:
            manifest = PluginManifest.model_validate_json(archive.read(manifest_name))
        except (ValidationError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PackageValidationError(f"invalid plugin.json: {exc}") from exc
        required = {
            manifest.runtime.entrypoint.casefold(): "runtime entrypoint",
            manifest.ui.entrypoint.casefold(): "UI entrypoint",
            manifest.package.sbom.casefold(): "SBOM",
        }
        if manifest.ui.settings_entrypoint:
            if PurePosixPath(manifest.ui.settings_entrypoint).parent != PurePosixPath(manifest.ui.entrypoint).parent:
                raise PackageValidationError("settings UI entrypoint must share the plugin UI root")
            required[manifest.ui.settings_entrypoint.casefold()] = "settings UI entrypoint"
        for required_name, label in required.items():
            if required_name not in names:
                raise PackageValidationError(f"manifest {label} is missing from package")
        if not any(PurePosixPath(item.filename).name.casefold().startswith("license") for item in members):
            raise PackageValidationError("plugin license inventory is missing")
        try:
            sbom = json.loads(archive.read(names[manifest.package.sbom.casefold()]))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PackageValidationError("plugin SBOM is not valid JSON") from exc
        if not isinstance(sbom, dict) or sbom.get("bomFormat") != "CycloneDX":
            raise PackageValidationError("plugin SBOM must use CycloneDX format")
        return manifest, members


def validate_manifest_entry(
    manifest: PluginManifest,
    entry: MarketplaceEntry,
    platform: str | None = None,
) -> None:
    if manifest.id != entry.id:
        raise PackageValidationError("manifest id does not match catalog entry")
    if manifest.publisher != entry.publisher_id:
        raise PackageValidationError("manifest publisher does not match catalog entry")
    if manifest.version != entry.latest_version:
        raise PackageValidationError("manifest version does not match catalog entry")
    if manifest.host_compatibility != entry.host_compatibility:
        raise PackageValidationError("manifest host compatibility does not match catalog entry")
    if platform is not None and entry.packages:
        # Per-platform packages: each zip's manifest declares its own platform
        # set; it must be covered by the entry and include the host platform.
        if set(manifest.platforms) - set(entry.platforms):
            raise PackageValidationError("manifest platforms exceed catalog entry platforms")
        if platform not in manifest.platforms:
            raise PackageValidationError(f"manifest has no package for platform: {platform}")
    elif sorted(manifest.platforms) != sorted(entry.platforms):
        raise PackageValidationError("manifest platforms do not match catalog entry")
    if sorted(manifest.permissions) != sorted(entry.permissions_summary):
        raise PackageValidationError("manifest permissions do not match catalog entry")


_SAMPLE_BYTES = 64 * 1024
_CRC_CHUNK_BYTES = 8 * 1024 * 1024


def _donor_matches_member(donor: Path, item: zipfile.ZipInfo, archive: zipfile.ZipFile) -> bool:
    """Decide whether an installed file from a previous version is byte-identical
    to this package member, so it can be hard-linked instead of re-written.

    Pipeline (cheapest first):
      1. donor exists as a file and the sizes agree (stat only);
      2. the first 64 KB agree (pre-filter: avoids full reads of files whose
         content changed at the head);
      3. the donor's full CRC32 equals the member's CRC32 (decisive; the zip
         CRC covers the whole file, so a middle-of-file change is caught even
         when head and tail are identical).

    Trust note: the donor tree is a previously installed, host-validated
    version directory; the new package itself was sha256-verified against the
    catalog pin before extraction. Reusing donor bytes via hard link adds no
    new trust surface (the installed tree is not re-verified by design).
    """
    try:
        donor_stat = donor.stat()
    except OSError:
        return False
    if not stat.S_ISREG(donor_stat.st_mode) or donor_stat.st_size != item.file_size:
        return False
    try:
        with _raw_path(donor).open("rb") as donor_file:
            head = donor_file.read(_SAMPLE_BYTES)
            if head != _member_prefix(archive, item, _SAMPLE_BYTES):
                return False
            # The decisive check covers the WHOLE file, including the head
            # sample just read.
            donor_file.seek(0)
            digest = _crc32_stream(donor_file)
    except OSError:
        return False
    return digest == (item.CRC & 0xFFFFFFFF)


def _member_prefix(archive: zipfile.ZipFile, item: zipfile.ZipInfo, count: int) -> bytes:
    with archive.open(item, "r") as source:
        return source.read(count)


def _crc32_stream(handle) -> int:
    value = 0
    while True:
        block = handle.read(_CRC_CHUNK_BYTES)
        if not block:
            return value
        value = zlib.crc32(block, value) & 0xFFFFFFFF


def extract_package(
    package_path: Path,
    target: Path,
    members: list[zipfile.ZipInfo],
    *,
    reuse_from: Path | None = None,
) -> int:
    """Extract the (already verified) package into ``target``.

    With ``reuse_from`` (a previous version's installed directory on the same
    volume), members byte-identical to files there are hard-linked instead of
    re-written: version upgrades stop paying the full unpack I/O and disk for
    unchanged files, and the old version directory is never modified
    (rollback keeps working). Any mismatch or link failure falls back to a
    normal extraction of that member — reuse is an optimization that can
    never change the resulting tree.

    Returns the number of members satisfied by hard links.
    """
    if target.exists():
        remove_tree(target)
    target.mkdir(parents=True, exist_ok=False)
    resolved_target = target.resolve()
    reuse_root = reuse_from.resolve() if reuse_from is not None and reuse_from.is_dir() else None
    reused = 0
    with zipfile.ZipFile(package_path, "r") as archive:
        for item in members:
            relative = _validate_member(item.filename)
            destination = (resolved_target / Path(*relative.parts)).resolve()
            try:
                destination.relative_to(resolved_target)
            except ValueError as exc:
                raise PackageValidationError(f"unsafe archive path: {item.filename!r}") from exc
            # Raw-prefixed for the filesystem ops: deep member paths can
            # exceed MAX_PATH on Windows (see _raw_path).
            _raw_path(destination.parent).mkdir(parents=True, exist_ok=True)
            if (
                reuse_root is not None
                and item.file_size > 0
                and _donor_matches_member(reuse_root / Path(*relative.parts), item, archive)
            ):
                try:
                    os.link(_raw_path(reuse_root / Path(*relative.parts)), _raw_path(destination))
                    reused += 1
                    continue
                except OSError:
                    pass  # cross-volume / permission: extract normally
            with archive.open(item, "r") as source, _raw_path(destination).open("xb") as output:
                shutil.copyfileobj(source, output)
    return reused

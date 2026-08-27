from __future__ import annotations

import json
import os
import shutil
import stat
import zipfile
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


def validate_manifest_entry(manifest: PluginManifest, entry: MarketplaceEntry) -> None:
    if manifest.id != entry.id:
        raise PackageValidationError("manifest id does not match catalog entry")
    if manifest.publisher != entry.publisher_id:
        raise PackageValidationError("manifest publisher does not match catalog entry")
    if manifest.version != entry.latest_version:
        raise PackageValidationError("manifest version does not match catalog entry")
    if manifest.host_compatibility != entry.host_compatibility:
        raise PackageValidationError("manifest host compatibility does not match catalog entry")
    if sorted(manifest.platforms) != sorted(entry.platforms):
        raise PackageValidationError("manifest platforms do not match catalog entry")
    if sorted(manifest.permissions) != sorted(entry.permissions_summary):
        raise PackageValidationError("manifest permissions do not match catalog entry")


def extract_package(package_path: Path, target: Path, members: list[zipfile.ZipInfo]) -> None:
    if target.exists():
        remove_tree(target)
    target.mkdir(parents=True, exist_ok=False)
    resolved_target = target.resolve()
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
            with archive.open(item, "r") as source, _raw_path(destination).open("xb") as output:
                shutil.copyfileobj(source, output)

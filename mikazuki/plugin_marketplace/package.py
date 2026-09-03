from __future__ import annotations

import json
import os
import shutil
import stat
import threading
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
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
# Extraction copy buffer: 1 MB (copyfileobj default) costs ~1000 loop
# iterations per 1 GB of large binaries; 8 MB cuts that ~8x with no memory
# cost that matters (one buffer per worker thread).
_EXTRACT_CHUNK_BYTES = 8 * 1024 * 1024
_EXTRACT_WORKERS_ENV = "MIKAZUKI_EXTRACT_WORKERS"
_EXTRACT_WORKERS_CAP = 16


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
        # Raw-prefixed stat: deep node_modules members can exceed MAX_PATH on
        # Windows, where a plain-path stat raises and would silently degrade
        # reuse to a full re-extract for every deep member.
        donor_stat = _raw_path(donor).stat()
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


def _extraction_worker_count(total: int, *, default: int = 8, cap: int = 16) -> int:
    """Adaptive fan-out for extraction (P1-2).

    Tiny packages gain nothing from a thread pool (zip open + scheduling cost
    would dominate); large trees are dominated by per-file system/AV overhead
    (P0 census: clean CRC pass ~161s vs ~9s for the links on a 36.8k-file
    upgrade), which is per-handle and parallelizes well, so the pool scales
    from the 8-worker default up to the 16-worker cap as the tree grows.
    """
    if total <= 0:
        return 1
    if total < 256:
        return max(1, min(default, (total + 31) // 32))
    return min(cap, default + (total - 256) // 4096)


def _extraction_workers_from_env() -> int | None:
    """Explicit operator opt-in for parallel extraction (P1-2 bench lesson).

    On the acceptance machine (NVMe + AV real-time scanning + a live host),
    the 16-worker pool measured ~2.3x SLOWER than serial (65-69s vs 110-193s
    for the 282MB / 36.8k-member package): per-file AV scans contend harder
    under concurrent writes than the CPU work parallelizes. The DEFAULT stays
    serial — identical to the pre-P1 behavior, zero regression risk — and
    parallel extraction is an opt-in: ``MIKAZUKI_EXTRACT_WORKERS=2..16``
    (clamped; invalid values fall back to the serial default).
    """
    raw = os.environ.get(_EXTRACT_WORKERS_ENV, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return max(1, min(value, _EXTRACT_WORKERS_CAP))


def extract_package(
    package_path: Path,
    target: Path,
    members: list[zipfile.ZipInfo],
    *,
    reuse_from: Path | None = None,
    max_workers: int | None = None,
) -> int:
    """Extract the (already verified) package into ``target``.

    With ``reuse_from`` (a previous version's installed directory on the same
    volume), members byte-identical to files there are hard-linked instead of
    re-written: version upgrades stop paying the full unpack I/O and disk for
    unchanged files, and the old version directory is never modified
    (rollback keeps working). Any mismatch or link failure falls back to a
    normal extraction of that member — reuse is an optimization that can
    never change the resulting tree.

    P1-2: extraction concurrency. The DEFAULT is serial (the exact pre-P1
    behavior). ``max_workers`` (or the ``MIKAZUKI_EXTRACT_WORKERS`` env,
    clamped to 1..16) opts into a thread pool: each worker keeps its own
    ``zipfile.ZipFile`` handle, and ``_extraction_worker_count`` sizes the
    pool adaptively for small packages. Bench note: on the acceptance
    machine (AV real-time scanning, live host) 16 workers measured ~2.3x
    SLOWER than serial — per-file AV scan contention under concurrent
    writes — so parallel stays an explicit opt-in, never a surprise.

    Every safety check still runs for every member before any file is
    written; a failure in any member fails the whole extraction (the first
    error is raised) and the caller's staging cleanup removes the partial
    tree — no half-finished version is ever left behind.

    Returns the number of members satisfied by hard links.
    """
    if target.exists():
        remove_tree(target)
    target.mkdir(parents=True, exist_ok=False)
    resolved_target = target.resolve()
    reuse_root = reuse_from.resolve() if reuse_from is not None and reuse_from.is_dir() else None

    # Pre-validate every member up front, single-threaded, before any
    # fan-out: an unsafe member fails the whole package exactly as the
    # serial loop did — and before any parallel file writes begin.
    prepared: list[tuple[zipfile.ZipInfo, Path, Path]] = []
    for item in members:
        relative = _validate_member(item.filename)
        destination = (resolved_target / Path(*relative.parts)).resolve()
        try:
            destination.relative_to(resolved_target)
        except ValueError as exc:
            raise PackageValidationError(f"unsafe archive path: {item.filename!r}") from exc
        prepared.append((item, relative, destination))

    reused_box = [0]
    reused_lock = threading.Lock()
    worker_state = threading.local()
    worker_archives: list[zipfile.ZipFile] = []
    archives_lock = threading.Lock()

    def _worker_archive() -> zipfile.ZipFile:
        # zipfile.ZipFile is not thread-safe; each worker thread keeps its
        # own read-only instance (the OS allows shared read handles).
        archive = getattr(worker_state, "archive", None)
        if archive is None:
            archive = zipfile.ZipFile(package_path, "r")
            worker_state.archive = archive
            with archives_lock:
                worker_archives.append(archive)
        return archive

    def _extract_one(item: zipfile.ZipInfo, relative: PurePosixPath, destination: Path) -> None:
        try:
            # Raw-prefixed for the filesystem ops: deep member paths can
            # exceed MAX_PATH on Windows (see _raw_path).
            _raw_path(destination.parent).mkdir(parents=True, exist_ok=True)
            linked = False
            if reuse_root is not None and item.file_size > 0:
                donor = reuse_root / Path(*relative.parts)
                if _donor_matches_member(donor, item, _worker_archive()):
                    try:
                        os.link(_raw_path(donor), _raw_path(destination))
                        linked = True
                    except OSError:
                        linked = False  # cross-volume / permission: extract normally
            if linked:
                with reused_lock:
                    reused_box[0] += 1
                return
            with _worker_archive().open(item, "r") as source, _raw_path(destination).open("xb") as output:
                shutil.copyfileobj(source, output, _EXTRACT_CHUNK_BYTES)
        except BaseException:
            # A worker that dies with an open handle would keep the zip busy;
            # close it on the error path (the success path is closed at the
            # end of the pool / by the serial context manager).
            archive = getattr(worker_state, "archive", None)
            if archive is not None:
                try:
                    archive.close()
                except Exception:
                    pass
                worker_state.archive = None
                with archives_lock:
                    if archive in worker_archives:
                        worker_archives.remove(archive)
            raise

    if max_workers is not None:
        workers = max_workers
    elif len(prepared) < 256:
        # Small packages: the pool would cost more than it saves (adaptive
        # sizing would pick 1 for these anyway).
        workers = 1
    else:
        # Default = serial (see docstring: AV-contention bench lesson).
        # MIKAZUKI_EXTRACT_WORKERS opts into the pool explicitly.
        workers = _extraction_workers_from_env() or 1
    workers = max(1, min(workers, _EXTRACT_WORKERS_CAP))

    try:
        if workers == 1:
            # Small packages: the exact legacy serial path (no pool, one
            # archive handle).
            with zipfile.ZipFile(package_path, "r") as archive:
                worker_state.archive = archive
                for item, relative, destination in prepared:
                    _extract_one(item, relative, destination)
        else:
            first_error: list[BaseException] = []
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="plugin-extract") as pool:
                futures = [pool.submit(_extract_one, item, relative, destination) for item, relative, destination in prepared]
                for future in futures:
                    try:
                        future.result()
                    except BaseException as exc:  # noqa: B035 - re-raised below
                        if not first_error:
                            first_error.append(exc)
            if first_error:
                raise first_error[0]
    finally:
        with archives_lock:
            for archive in worker_archives:
                try:
                    archive.close()
                except Exception:
                    pass
    return reused_box[0]

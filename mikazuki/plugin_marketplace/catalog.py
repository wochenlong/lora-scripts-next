from __future__ import annotations

import hashlib
import http.client
import json
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urlsplit

from pydantic import ValidationError

from .models import MarketplaceCatalog, MarketplaceEntry
from .paths import MarketplacePaths
from .trust import TrustError, TrustStore


_COPY_CHUNK_BYTES = 8 * 1024 * 1024
_HTTP_CHUNK_BYTES = 1 * 1024 * 1024
_HTTP_MAX_ATTEMPTS = 6
_HTTP_BACKOFF_BASE_S = 1.0
_HTTP_BACKOFF_CAP_S = 16.0
_HTTP_STALL_TIMEOUT_S = 60.0


class CatalogError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.status_code = status_code


class CatalogSource(Protocol):
    def read(self) -> bytes: ...


class PackageAcquirer(Protocol):
    def acquire(
        self,
        entry: MarketplaceEntry,
        destination: Path,
        platform: str,
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Path: ...


class FileCatalogSource:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def read(self) -> bytes:
        try:
            return self.path.read_bytes()
        except OSError as exc:
            raise CatalogError(
                "MARKETPLACE_CATALOG_OFFLINE",
                "The marketplace catalog is unavailable.",
                status_code=503,
            ) from exc


class HttpCatalogSource:
    """Online catalog fetch (the release update channel).

    Transport is untrusted by design: the service verifies the catalog
    signature on every refresh and only replaces the local cache after the
    signature passes, so a hostile path can only ever deliver payloads that
    fail verification. Plain HTTP is accepted loopback-only, mirroring the
    package-mirror rule for local development and release dry-runs.
    """

    max_response_bytes = 4 * 1024 * 1024  # catalogs are tiny; cap defensively

    def __init__(self, url: str, *, timeout_seconds: float = 15.0) -> None:
        url = url.strip()
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("catalog URL must be a plain http(s) URL without credentials")
        if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("plain-HTTP catalog URLs must be loopback-only")
        self.url = url
        self.timeout_seconds = timeout_seconds

    def read(self) -> bytes:
        try:
            request = urllib.request.Request(self.url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read(self.max_response_bytes + 1)
        except (urllib.error.URLError, OSError) as exc:
            raise CatalogError(
                "MARKETPLACE_CATALOG_OFFLINE",
                "The marketplace catalog could not be downloaded.",
                status_code=503,
            ) from exc
        if len(payload) > self.max_response_bytes:
            raise CatalogError(
                "MARKETPLACE_CATALOG_TOO_LARGE",
                "The downloaded marketplace catalog exceeds the size limit.",
                status_code=502,
            )
        return payload


class FallbackCatalogSource:
    """Try each source in priority order and return the first readable payload.

    The default wiring composes [HttpCatalogSource, FileCatalogSource] so a
    bundled release catalog keeps a fresh offline install working while the
    live signed catalog wins whenever it is reachable. When every source
    fails, the first error is re-raised so the offline code stays intact.
    """

    def __init__(self, *sources: CatalogSource | None) -> None:
        self.sources = [source for source in sources if source is not None]

    def read(self) -> bytes:
        first_error: CatalogError | None = None
        for source in self.sources:
            try:
                return source.read()
            except CatalogError as exc:
                first_error = first_error or exc
        raise first_error or CatalogError(
            "MARKETPLACE_CATALOG_OFFLINE",
            "The marketplace catalog is unavailable.",
            status_code=503,
        )


class LocalPackageAcquirer:
    """Stage 1/offline acquisition from a Host-approved immutable URL map."""

    def __init__(self, sources: dict[str, Path]) -> None:
        self._sources = {url: path.resolve() for url, path in sources.items()}

    @property
    def source_urls(self) -> frozenset[str]:
        return frozenset(self._sources)

    def acquire(
        self,
        entry: MarketplaceEntry,
        destination: Path,
        platform: str,
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        try:
            package_url, package_size, _sha256 = entry.resolve_platform_package(platform)
        except ValueError as exc:
            raise CatalogError(
                "MARKETPLACE_PLATFORM_UNAVAILABLE",
                "The marketplace has no package for this platform.",
                status_code=409,
            ) from exc
        source = self._sources.get(package_url)
        if source is None or not source.is_file():
            raise CatalogError(
                "MARKETPLACE_PACKAGE_UNAVAILABLE",
                "The marketplace package is unavailable.",
                status_code=503,
            )
        if source.stat().st_size != package_size:
            raise CatalogError(
                "MARKETPLACE_PACKAGE_SIZE_MISMATCH",
                "The marketplace package size does not match the catalog.",
                status_code=400,
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        if on_progress is not None:
            on_progress(0, package_size)
        current = 0
        try:
            with source.open("rb") as handle_in, temporary.open("wb") as handle_out:
                while True:
                    if is_cancelled is not None and is_cancelled():
                        raise CatalogError(
                            "MARKETPLACE_OPERATION_CANCELLED",
                            "The plugin installation was cancelled.",
                            status_code=409,
                        )
                    chunk = handle_in.read(_COPY_CHUNK_BYTES)
                    if not chunk:
                        break
                    handle_out.write(chunk)
                    current += len(chunk)
                    if on_progress is not None:
                        on_progress(current, package_size)
                handle_out.flush()
                os.fsync(handle_out.fileno())
            os.replace(temporary, destination)
        except CatalogError:
            raise
        except OSError as exc:
            raise CatalogError(
                "MARKETPLACE_PACKAGE_ACQUISITION_FAILED",
                "The marketplace package could not be acquired.",
                status_code=503,
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)
        return destination


def _cancelled_error() -> CatalogError:
    return CatalogError(
        "MARKETPLACE_OPERATION_CANCELLED",
        "The plugin installation was cancelled.",
        status_code=409,
    )


class HttpPackageAcquirer:
    """Online acquisition from the catalog's HTTPS package URL.

    The URL may be rewritten onto a host-approved mirror base URL (the
    ``MIKAZUKI_MARKETPLACE_PACKAGE_MIRROR`` environment value in the default
    wiring). A plain-HTTP mirror must be loopback-only: it exists for local
    development and release dry-runs, and integrity still comes from the
    catalog-pinned size + sha256, so a loopback mirror cannot smuggle a
    tampered package into the quarantine.

    Transient failures (transport errors, 5xx, stalled connections) are
    retried with exponential backoff and **Range resumption**: a partial
    ``.part`` file is kept and the next attempt requests ``bytes=N-``.
    Resumption never weakens integrity — the final sha256 always covers the
    whole object (the retained prefix is re-hashed when seeding a resumed
    digest), and any integrity failure drops the ``.part`` for a clean
    full re-download. Servers that ignore ``Range`` (200 instead of 206) or
    reject it (416) fall back to a full re-download.

    A stalled connection is detected by the socket timeout (``stall_timeout_s``):
    if no bytes arrive for that whole window the read raises and the attempt
    is treated as a transient interruption. Reads run on the calling thread
    (no worker thread) so the socket is always closed by its owner — a
    cross-thread close would block on Windows until the remote end closes.
    Cancellation is therefore observed between chunks: instant on a live
    transfer, within one stall window on a dead one.
    """

    def __init__(
        self,
        mirror_base_url: str | None = None,
        *,
        max_attempts: int = _HTTP_MAX_ATTEMPTS,
        backoff_base_s: float = _HTTP_BACKOFF_BASE_S,
        backoff_cap_s: float = _HTTP_BACKOFF_CAP_S,
        stall_timeout_s: float = _HTTP_STALL_TIMEOUT_S,
    ) -> None:
        self._mirror = self._validate_mirror(mirror_base_url)
        self._max_attempts = max_attempts
        self._backoff_base_s = backoff_base_s
        self._backoff_cap_s = backoff_cap_s
        self._stall_timeout_s = stall_timeout_s

    @staticmethod
    def _validate_mirror(mirror: str | None) -> str | None:
        if mirror is None or not mirror.strip():
            return None
        mirror = mirror.strip()
        parsed = urlsplit(mirror)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("mirror base URL must be a plain http(s) URL without credentials")
        if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("plain-HTTP mirrors must be loopback-only")
        return mirror.rstrip("/")

    def _resolve(self, entry: MarketplaceEntry, platform: str) -> tuple[str, int, str]:
        try:
            package_url, package_size, sha256 = entry.resolve_platform_package(platform)
        except ValueError as exc:
            raise CatalogError(
                "MARKETPLACE_PLATFORM_UNAVAILABLE",
                "The marketplace has no package for this platform.",
                status_code=409,
            ) from exc
        if self._mirror is None:
            return package_url, package_size, sha256
        path = urlsplit(package_url).path
        return f"{self._mirror}{path}", package_size, sha256

    def acquire(
        self,
        entry: MarketplaceEntry,
        destination: Path,
        platform: str,
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        url, package_size, sha256 = self._resolve(entry, platform)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        last_error: CatalogError | None = None
        for attempt in range(1, self._max_attempts + 1):
            if is_cancelled is not None and is_cancelled():
                raise _cancelled_error()
            if attempt > 1:
                delay = min(self._backoff_base_s * 2 ** (attempt - 2), self._backoff_cap_s)
                if delay > 0:
                    time.sleep(delay)
            try:
                self._download(url, temporary, package_size, sha256, on_progress, is_cancelled)
                break
            except CatalogError as exc:
                # Integrity failures mean the bytes on disk cannot be trusted:
                # drop the partial file so any later attempt starts clean.
                # On transient failures the .part is KEPT for Range resume.
                if exc.code in ("MARKETPLACE_PACKAGE_SIZE_MISMATCH", "MARKETPLACE_PACKAGE_CHECKSUM_MISMATCH"):
                    temporary.unlink(missing_ok=True)
                # Cancellation, unavailability and final integrity errors are
                # not retryable; only transient transport / server errors are
                # (resumable). The acquirer still cleans its own .part before
                # surfacing a terminal failure (the service-layer sweep stays
                # as the lock-race backstop from the V30 .part finding).
                if exc.code != "MARKETPLACE_PACKAGE_ACQUISITION_FAILED":
                    temporary.unlink(missing_ok=True)
                    raise
                last_error = exc
        else:
            temporary.unlink(missing_ok=True)
            raise last_error or CatalogError(
                "MARKETPLACE_PACKAGE_ACQUISITION_FAILED",
                "The marketplace package could not be acquired.",
                status_code=503,
            )
        os.replace(temporary, destination)
        return destination

    def _download(
        self,
        url: str,
        temporary: Path,
        package_size: int,
        sha256: str,
        on_progress: Callable[[int, int], None] | None,
        is_cancelled: Callable[[], bool] | None,
    ) -> None:
        # Resume from a retained partial file when the pin still fits it.
        # (The quarantine path is per plugin+version, so a .part here always
        # belongs to the same pinned object; a stale object's bytes are
        # caught by the final whole-object sha256 below.)
        resume_from = 0
        if temporary.is_file():
            existing = temporary.stat().st_size
            if 0 < existing < package_size:
                resume_from = existing
        start_current = resume_from
        # Whether the retained prefix is still the basis of this attempt.
        # Fallbacks below (server ignored / rejected the range) restart from
        # zero, which invalidates the prefix for checksum semantics.
        prefix_active = resume_from > 0
        digest = hashlib.sha256()
        if resume_from:
            # Seed the digest with the retained prefix so the final sha256
            # still covers the whole object — resumption never skips checks.
            with temporary.open("rb") as handle:
                while True:
                    block = handle.read(_COPY_CHUNK_BYTES)
                    if not block:
                        break
                    digest.update(block)
        headers = {"User-Agent": "next-trainer-marketplace/1.0"}
        if resume_from:
            headers["Range"] = f"bytes={resume_from}-"
        request = urllib.request.Request(url, headers=headers)
        declared_length: int | None = None
        try:
            # The socket timeout IS the stall detector: no bytes for the whole
            # window raises socket.timeout, which maps to a transient failure
            # below (the .part is kept for resumption). It also bounds the
            # header/connect wait.
            with urllib.request.urlopen(request, timeout=self._stall_timeout_s) as handle:
                status = getattr(handle, "status", None)
                if status is None:
                    status = handle.getcode()
                length_raw = handle.headers.get("Content-Length")
                if length_raw is not None:
                    try:
                        declared_length = int(length_raw)
                    except ValueError:
                        declared_length = None
                current = resume_from
                # Append only when a validated prefix is being resumed;
                # otherwise truncate so a stale/oversized .part can never
                # contaminate the new object.
                mode = "ab" if resume_from > 0 else "wb"
                if status == 200 and resume_from:
                    # Server ignored Range: it re-sends from zero, so the
                    # retained prefix must not be appended to.
                    current = 0
                    start_current = 0
                    mode = "wb"
                    digest = hashlib.sha256()
                    prefix_active = False
                elif status == 206 and resume_from:
                    content_range = (handle.headers.get("Content-Range") or "").strip()
                    if content_range and f"/{package_size}" not in content_range:
                        # The server's object is a different size than the
                        # catalog pin: the retained prefix is invalid.
                        current = 0
                        start_current = 0
                        mode = "wb"
                        digest = hashlib.sha256()
                        prefix_active = False
                with temporary.open(mode) as out:
                    if on_progress is not None:
                        on_progress(current, package_size)
                    while True:
                        if is_cancelled is not None and is_cancelled():
                            raise _cancelled_error()
                        try:
                            chunk = handle.read(_HTTP_CHUNK_BYTES)
                        except socket.timeout:
                            # No bytes for the whole stall window: the
                            # connection is dead or frozen. Transient — the
                            # .part is kept and the next attempt resumes.
                            raise CatalogError(
                                "MARKETPLACE_PACKAGE_ACQUISITION_FAILED",
                                "The marketplace package could not be acquired.",
                                status_code=503,
                            )
                        if not chunk:
                            break
                        digest.update(chunk)
                        current += len(chunk)
                        out.write(chunk)
                        if on_progress is not None:
                            on_progress(current, package_size)
                    out.flush()
                    os.fsync(out.fileno())
        except CatalogError:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                raise CatalogError(
                    "MARKETPLACE_PACKAGE_UNAVAILABLE",
                    "The marketplace package is unavailable.",
                    status_code=404 if exc.code == 404 else 503,
                ) from exc
            if exc.code == 416:
                # Resume range no longer satisfiable (object changed on the
                # server): the retained prefix is invalid — drop it so the
                # next attempt restarts from zero.
                temporary.unlink(missing_ok=True)
            raise CatalogError(
                "MARKETPLACE_PACKAGE_ACQUISITION_FAILED",
                "The marketplace package could not be acquired.",
                status_code=503,
            ) from exc
        except (urllib.error.URLError, http.client.HTTPException, socket.timeout, OSError) as exc:
            raise CatalogError(
                "MARKETPLACE_PACKAGE_ACQUISITION_FAILED",
                "The marketplace package could not be acquired.",
                status_code=503,
            ) from exc
        received = current - start_current
        if current != package_size:
            # A *complete* response whose declared body length was honored
            # means the object is genuinely short: the catalog pin is wrong
            # and retrying cannot fix it. Anything else (declared body cut
            # short, undeclared/chunked EOF) is an interrupted transfer —
            # transient, and the .part is kept for resumption.
            if declared_length is not None and received == declared_length:
                raise CatalogError(
                    "MARKETPLACE_PACKAGE_SIZE_MISMATCH",
                    "The marketplace package size does not match the catalog.",
                    status_code=400,
                )
            raise CatalogError(
                "MARKETPLACE_PACKAGE_ACQUISITION_FAILED",
                "The marketplace package could not be acquired.",
                status_code=503,
            )
        if digest.hexdigest().casefold() != sha256.casefold():
            if prefix_active:
                # The failure happened on top of a retained prefix: the
                # prefix (or the resumed tail) may be locally corrupted, so
                # dropping it and re-downloading from zero can succeed.
                # Surface it as transient; the next attempt starts fresh,
                # and a fresh-attempt mismatch below is terminal.
                temporary.unlink(missing_ok=True)
                raise CatalogError(
                    "MARKETPLACE_PACKAGE_ACQUISITION_FAILED",
                    "The marketplace package could not be acquired.",
                    status_code=503,
                )
            raise CatalogError(
                "MARKETPLACE_PACKAGE_CHECKSUM_MISMATCH",
                "The marketplace package checksum does not match the catalog.",
                status_code=400,
            )


class LocalFirstPackageAcquirer:
    """Prefer the host-approved local package map, then fall through to HTTP.

    Development and bundled releases address packages through the local map
    (fast, offline); release builds whose local map does not cover the
    catalog URL download it from the mirror/HTTPS origin instead.
    """

    def __init__(self, local: LocalPackageAcquirer, remote: HttpPackageAcquirer) -> None:
        self.local = local
        self.remote = remote

    def acquire(
        self,
        entry: MarketplaceEntry,
        destination: Path,
        platform: str,
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        try:
            return self.local.acquire(entry, destination, platform, on_progress, is_cancelled)
        except CatalogError as exc:
            # Only "no local copy" falls through; size/integrity failures of a
            # local copy are hard errors and must not be masked by a download.
            if exc.code != "MARKETPLACE_PACKAGE_UNAVAILABLE":
                raise
            return self.remote.acquire(entry, destination, platform, on_progress, is_cancelled)


class UnavailablePackageAcquirer:
    def acquire(
        self,
        entry: MarketplaceEntry,
        destination: Path,
        platform: str,
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        raise CatalogError(
            "MARKETPLACE_PACKAGE_ACQUISITION_UNAVAILABLE",
            "Marketplace package acquisition is not configured.",
            status_code=503,
        )


class MarketplaceCatalogService:
    def __init__(
        self,
        *,
        paths: MarketplacePaths,
        trust: TrustStore,
        source: CatalogSource | None = None,
        acquirer: PackageAcquirer | None = None,
    ) -> None:
        self.paths = paths
        self.trust = trust
        self.source = source
        self.acquirer = acquirer or UnavailablePackageAcquirer()

    def refresh(self) -> MarketplaceCatalog:
        if self.source is None:
            raise CatalogError(
                "MARKETPLACE_CATALOG_OFFLINE",
                "The marketplace catalog is unavailable.",
                status_code=503,
            )
        catalog = self._parse(self.source.read())
        try:
            self.trust.verify_catalog(catalog)
        except TrustError as exc:
            raise CatalogError(
                "MARKETPLACE_CATALOG_UNTRUSTED",
                "The marketplace catalog could not be verified.",
                status_code=503,
            ) from exc
        self._write_cache(catalog)
        return catalog

    def catalog(self) -> MarketplaceCatalog:
        try:
            payload = self.paths.catalog_cache_file.read_bytes()
        except OSError as exc:
            raise CatalogError(
                "MARKETPLACE_CATALOG_OFFLINE",
                "The marketplace catalog is unavailable.",
                status_code=503,
            ) from exc
        catalog = self._parse(payload)
        try:
            self.trust.verify_catalog(catalog)
        except TrustError as exc:
            raise CatalogError(
                "MARKETPLACE_CATALOG_UNTRUSTED",
                "The marketplace catalog could not be verified.",
                status_code=503,
            ) from exc
        return catalog

    def list_entries(self) -> list[MarketplaceEntry]:
        return sorted(self.catalog().entries, key=lambda entry: (entry.name.casefold(), entry.id, entry.latest_version))

    def entry(self, plugin_id: str, version: str | None = None) -> MarketplaceEntry:
        matches = [
            entry
            for entry in self.catalog().entries
            if entry.id == plugin_id and (version is None or entry.latest_version == version)
        ]
        if len(matches) != 1:
            raise CatalogError(
                "MARKETPLACE_ENTRY_NOT_FOUND",
                "The marketplace plugin entry was not found.",
                status_code=404,
            )
        return matches[0]

    def acquire(
        self,
        entry: MarketplaceEntry,
        platform: str,
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        """Fetch the platform package into the PERSISTENT package cache.

        The cache location (``paths.quarantine_package``) outlives the install
        operation: a cancelled or failed install leaves the verified zip in
        place, and a later install of the same catalog-pinned package reuses
        it without any network or local-copy traffic (V30 UX fix: cancelling
        during extraction must not cost a second download).
        """
        destination = self.paths.quarantine_package(entry.id, entry.latest_version)
        try:
            _url, expected_size, expected_sha = entry.resolve_platform_package(platform)
        except ValueError:
            _url, expected_size, expected_sha = None, None, None
        if destination.is_file() and expected_sha is not None:
            try:
                if destination.stat().st_size == expected_size and self._file_sha256(destination) == expected_sha.lower():
                    if on_progress is not None:
                        try:
                            on_progress(expected_size, expected_size)
                        except Exception:  # noqa: BLE001 — cached hit must never break the install
                            pass
                    self._drop_stale_part(destination)
                    self._prune_package_caches(entry.id, keep=destination.name)
                    return destination
            except OSError:
                pass  # unreadable cache file -> re-acquire below
        destination.unlink(missing_ok=True)
        try:
            acquired = self.acquirer.acquire(entry, destination, platform, on_progress, is_cancelled)
        except BaseException:
            # Belt-and-braces for platform file-lock races in the acquirer's own
            # .part cleanup (observed once on Windows live acceptance, V30): a
            # stray .part must never linger next to the persistent cache.
            self._drop_stale_part(destination)
            raise
        self._drop_stale_part(destination)
        self._prune_package_caches(entry.id, keep=destination.name)
        return acquired

    @staticmethod
    def _drop_stale_part(destination: Path) -> None:
        """Best-effort removal of the acquirer's ``<name>.part`` temp file.

        The acquirer normally unlinks its own temp on cancel/failure; this
        closes the residual race on platforms where a transient lock makes
        that unlink fail (Windows live acceptance, V30: a 3 MiB .part
        survived a cancelled download). Cache zip and other plugins' files
        are never touched; failures are swallowed by design (cache hygiene,
        never install-critical).
        """
        try:
            (destination.parent / (destination.name + ".part")).unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_COPY_CHUNK_BYTES), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _prune_package_caches(self, plugin_id: str, *, keep: str) -> None:
        """Drop cached zips of superseded versions of the same plugin.

        Best-effort only: the cache is a UX optimization, pruning must never
        fail an install, and the KEEP file is never touched.
        """
        directory = self.paths.quarantine_packages(plugin_id)
        try:
            members = sorted(directory.iterdir())
        except OSError:
            return
        for member in members:
            try:
                if member.name != keep and member.is_file() and member.suffix == ".zip":
                    member.unlink(missing_ok=True)
            except OSError:
                continue

    @staticmethod
    def _parse(payload: bytes) -> MarketplaceCatalog:
        if len(payload) > 16 * 1024 * 1024:
            raise CatalogError(
                "MARKETPLACE_CATALOG_INVALID",
                "The marketplace catalog is invalid.",
                status_code=503,
            )
        try:
            return MarketplaceCatalog.model_validate_json(payload)
        except (ValidationError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CatalogError(
                "MARKETPLACE_CATALOG_INVALID",
                "The marketplace catalog is invalid.",
                status_code=503,
            ) from exc

    def _write_cache(self, catalog: MarketplaceCatalog) -> None:
        path = self.paths.catalog_cache_file
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        payload = json.dumps(
            catalog.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


__all__ = [
    "CatalogError",
    "FileCatalogSource",
    "HttpPackageAcquirer",
    "LocalFirstPackageAcquirer",
    "LocalPackageAcquirer",
    "MarketplaceCatalogService",
    "PackageAcquirer",
    "UnavailablePackageAcquirer",
]

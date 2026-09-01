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
_HTTP_TIMEOUT_S = 30
_HTTP_EXTRA_ATTEMPTS = 2


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
    """

    def __init__(self, mirror_base_url: str | None = None) -> None:
        self._mirror = self._validate_mirror(mirror_base_url)

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
        for attempt in range(_HTTP_EXTRA_ATTEMPTS + 1):
            if is_cancelled is not None and is_cancelled():
                raise _cancelled_error()
            if attempt:
                time.sleep(0.5 * attempt)
                if on_progress is not None:
                    on_progress(0, package_size)
            try:
                self._download(url, temporary, package_size, sha256, on_progress, is_cancelled)
                break
            except CatalogError as exc:
                temporary.unlink(missing_ok=True)
                # Cancellation, integrity failures and 404s are not retryable;
                # only transient transport / server errors (503 family) are.
                if exc.code != "MARKETPLACE_PACKAGE_ACQUISITION_FAILED":
                    raise
                last_error = exc
        else:
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
        digest = hashlib.sha256()
        current = 0
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "next-trainer-marketplace/1.0"})
            with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) as handle, temporary.open("wb") as out:
                if on_progress is not None:
                    on_progress(0, package_size)
                while True:
                    if is_cancelled is not None and is_cancelled():
                        raise _cancelled_error()
                    chunk = handle.read(_HTTP_CHUNK_BYTES)
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
        if current != package_size:
            raise CatalogError(
                "MARKETPLACE_PACKAGE_SIZE_MISMATCH",
                "The marketplace package size does not match the catalog.",
                status_code=400,
            )
        if digest.hexdigest().casefold() != sha256.casefold():
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
                    self._prune_package_caches(entry.id, keep=destination.name)
                    return destination
            except OSError:
                pass  # unreadable cache file -> re-acquire below
        destination.unlink(missing_ok=True)
        acquired = self.acquirer.acquire(entry, destination, platform, on_progress, is_cancelled)
        self._prune_package_caches(entry.id, keep=destination.name)
        return acquired

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

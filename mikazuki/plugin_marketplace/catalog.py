from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Protocol

from pydantic import ValidationError

from .models import MarketplaceCatalog, MarketplaceEntry
from .paths import MarketplacePaths
from .trust import TrustError, TrustStore


_COPY_CHUNK_BYTES = 8 * 1024 * 1024


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


class LocalPackageAcquirer:
    """Stage 1/offline acquisition from a Host-approved immutable URL map."""

    def __init__(self, sources: dict[str, Path]) -> None:
        self._sources = {url: path.resolve() for url, path in sources.items()}

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
        destination = self.paths.quarantine_package(entry.id, entry.latest_version)
        destination.unlink(missing_ok=True)
        return self.acquirer.acquire(entry, destination, platform, on_progress, is_cancelled)

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
    "LocalPackageAcquirer",
    "MarketplaceCatalogService",
    "PackageAcquirer",
]

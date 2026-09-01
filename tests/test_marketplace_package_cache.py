"""V30 persistent package cache: cancelled/failed installs must not lose the
verified download, and a re-install of the same pinned package must not
re-download it (user acceptance: "cancelling during extraction keeps the
package on the user side").

Covers the service-level cache (MarketplaceCatalogService.acquire), cache
pruning, and the startup cleanup semantics (verified zips kept, ``*.part``
temps removed).
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

import pytest

from mikazuki.plugin_marketplace.catalog import (
    CatalogError,
    MarketplaceCatalogService,
)
from mikazuki.plugin_marketplace.models import MarketplaceEntry
from mikazuki.plugin_marketplace.paths import MarketplacePaths
from mikazuki.plugin_marketplace.trust import TrustStore, canonical_entry_payload

KEY = b"test-cache-key"
URL = "https://plugins.next-trainer.local/packages/pkg.zip"
PAYLOAD = b"cached-plugin-bytes" * 50_000


def _build_entry(version: str = "1.0.0") -> MarketplaceEntry:
    digest = hashlib.sha256(PAYLOAD).hexdigest()
    value = {
        "id": "cache-plugin",
        "name": "Cache Plugin",
        "publisher_id": "approved-publisher-id",
        "latest_version": version,
        "channel": "stable",
        "host_compatibility": ">=2.9.2 <3.0.0",
        "platforms": ["win32-x64"],
        "package_size": len(PAYLOAD),
        "permissions_summary": [],
        "license": "MIT",
        "package_url": URL,
        "sha256": digest,
        "signature": "",
        "signing_key_id": "test-key",
        "published_at": "2026-09-01T00:00:00Z",
    }
    unsigned = MarketplaceEntry.model_validate(value)
    value["signature"] = hmac.new(KEY, canonical_entry_payload(unsigned), hashlib.sha256).hexdigest()
    return MarketplaceEntry.model_validate(value)


class _CountingAcquirer:
    """Fake acquirer: writes the expected payload, counts invocations."""

    def __init__(self, payload: bytes = PAYLOAD) -> None:
        self.calls = 0
        self.payload = payload

    def acquire(
        self,
        entry: MarketplaceEntry,
        destination: Path,
        platform: str,
        on_progress=None,
        is_cancelled=None,
    ) -> Path:
        self.calls += 1
        if is_cancelled is not None and is_cancelled():
            temporary = destination.with_suffix(destination.suffix + ".part")
            temporary.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(self.payload[: len(self.payload) // 2])
            temporary.unlink(missing_ok=True)
            raise CatalogError("MARKETPLACE_OPERATION_CANCELLED", "The plugin installation was cancelled.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.payload)
        return destination


class _FailingAfterDownloadAcquirer(_CountingAcquirer):
    """Acquire succeeds (zip lands in cache) — used to simulate the
    download-then-cancel-during-extraction sequence at the service level."""


def _service(tmp_path: Path, acquirer) -> tuple[MarketplaceCatalogService, MarketplacePaths]:
    paths = MarketplacePaths(tmp_path / "root")
    service = MarketplaceCatalogService(
        paths=paths,
        trust=TrustStore({}),
        source=None,
        acquirer=acquirer,
    )
    return service, paths


def test_first_acquire_downloads_second_acquire_is_cache_hit(tmp_path: Path):
    acquirer = _CountingAcquirer()
    service, paths = _service(tmp_path, acquirer)
    entry = _build_entry()

    first = service.acquire(entry, "win32-x64")
    assert first == paths.quarantine_package("cache-plugin", "1.0.0")
    assert first.read_bytes() == PAYLOAD
    assert acquirer.calls == 1

    second = service.acquire(entry, "win32-x64")
    assert second == first
    assert second.read_bytes() == PAYLOAD
    assert acquirer.calls == 1  # cache hit: no second download


def test_cache_hit_reports_full_progress(tmp_path: Path):
    acquirer = _CountingAcquirer()
    service, _ = _service(tmp_path, acquirer)
    entry = _build_entry()
    service.acquire(entry, "win32-x64")

    samples: list[tuple[int, int]] = []
    service.acquire(entry, "win32-x64", on_progress=lambda c, t: samples.append((c, t)))
    assert acquirer.calls == 1
    assert samples == [(len(PAYLOAD), len(PAYLOAD))]


def test_stale_cache_bytes_force_reacquire(tmp_path: Path):
    acquirer = _CountingAcquirer()
    service, paths = _service(tmp_path, acquirer)
    entry = _build_entry()
    cache = paths.quarantine_package("cache-plugin", "1.0.0")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"x" * len(PAYLOAD))  # same size, wrong content

    result = service.acquire(entry, "win32-x64")
    assert acquirer.calls == 1
    assert result.read_bytes() == PAYLOAD


def test_wrong_size_cache_forces_reacquire(tmp_path: Path):
    acquirer = _CountingAcquirer()
    service, paths = _service(tmp_path, acquirer)
    entry = _build_entry()
    cache = paths.quarantine_package("cache-plugin", "1.0.0")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"short")

    result = service.acquire(entry, "win32-x64")
    assert acquirer.calls == 1
    assert result.read_bytes() == PAYLOAD


def test_cancelled_download_leaves_no_cache_and_retries_next_time(tmp_path: Path):
    acquirer = _CountingAcquirer()
    service, paths = _service(tmp_path, acquirer)
    entry = _build_entry()

    with pytest.raises(CatalogError) as excinfo:
        service.acquire(entry, "win32-x64", is_cancelled=lambda: True)
    assert excinfo.value.code == "MARKETPLACE_OPERATION_CANCELLED"
    cache = paths.quarantine_package("cache-plugin", "1.0.0")
    assert not cache.exists()
    assert not cache.with_suffix(".zip.part").exists()

    # Retry after the user gives up on cancelling: a fresh download happens.
    result = service.acquire(entry, "win32-x64")
    assert acquirer.calls == 2
    assert result.read_bytes() == PAYLOAD


def test_cancelled_extraction_keeps_verified_package_for_retry(tmp_path: Path):
    """The user-reported scenario: download completes, the user cancels during
    extraction. The verified zip must survive so the retry skips the download.
    (The pipeline no longer unlinks the package; the service reuses it.)"""
    acquirer = _FailingAfterDownloadAcquirer()
    service, paths = _service(tmp_path, acquirer)
    entry = _build_entry()

    package = service.acquire(entry, "win32-x64")
    assert acquirer.calls == 1
    # ...install/extraction is cancelled or fails (zip untouched on purpose)...
    assert package.is_file()

    service2, _ = _service(tmp_path, _CountingAcquirer())
    assert acquirer.calls == 1
    again = service2.acquire(entry, "win32-x64")
    assert again == package
    assert again.read_bytes() == PAYLOAD
    # A brand-new acquirer is never consulted: the retry is download-free.


def test_prune_drops_superseded_version_keeps_current(tmp_path: Path):
    acquirer = _CountingAcquirer()
    service, paths = _service(tmp_path, acquirer)
    old_entry = _build_entry("0.9.0")
    new_entry = _build_entry("1.0.0")
    old_cache = paths.quarantine_package("cache-plugin", "0.9.0")
    old_cache.parent.mkdir(parents=True, exist_ok=True)
    old_cache.write_bytes(PAYLOAD)

    service.acquire(new_entry, "win32-x64")
    assert not old_cache.exists()
    assert paths.quarantine_package("cache-plugin", "1.0.0").is_file()


def test_prune_never_touches_other_plugins(tmp_path: Path):
    acquirer = _CountingAcquirer()
    service, paths = _service(tmp_path, acquirer)
    foreign = paths.quarantine_root / "other-plugin" / "1.0.0.zip"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_bytes(PAYLOAD)

    service.acquire(_build_entry(), "win32-x64")
    assert foreign.is_file()


class _LeakyPartAcquirer(_CountingAcquirer):
    """Simulates the platform file-lock race observed on Windows live
    acceptance (V30): the acquirer's own ``.part`` cleanup fails, so the
    temp file survives the cancelled/failing acquire. The SERVICE layer must
    still sweep it so a stray ``.part`` never lingers beside the cache."""

    def acquire(
        self,
        entry: MarketplaceEntry,
        destination: Path,
        platform: str,
        on_progress=None,
        is_cancelled=None,
    ) -> Path:
        self.calls += 1
        temporary = destination.with_suffix(destination.suffix + ".part")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(self.payload[:100])
        # the .part is deliberately left behind
        raise CatalogError("MARKETPLACE_OPERATION_CANCELLED", "The plugin installation was cancelled.")


def test_cancelled_download_with_leaky_part_is_swept(tmp_path: Path):
    acquirer = _LeakyPartAcquirer()
    service, paths = _service(tmp_path, acquirer)
    entry = _build_entry()
    cache = paths.quarantine_package("cache-plugin", "1.0.0")

    with pytest.raises(CatalogError) as excinfo:
        service.acquire(entry, "win32-x64")
    assert excinfo.value.code == "MARKETPLACE_OPERATION_CANCELLED"
    assert not cache.exists()
    assert not cache.with_suffix(".zip.part").exists()  # service swept the acquirer leak


def test_cache_hit_sweeps_stale_part(tmp_path: Path):
    acquirer = _CountingAcquirer()
    service, paths = _service(tmp_path, acquirer)
    entry = _build_entry()
    cache = paths.quarantine_package("cache-plugin", "1.0.0")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(PAYLOAD)
    part = cache.with_suffix(".zip.part")
    part.write_bytes(PAYLOAD[:10])

    result = service.acquire(entry, "win32-x64")
    assert result == cache
    assert acquirer.calls == 0  # pure cache hit
    assert not part.exists()


def test_startup_cleanup_keeps_verified_zip_removes_part(tmp_path: Path):
    from mikazuki.plugin_marketplace.api import _cleanup_stale_install_artifacts

    paths = MarketplacePaths(tmp_path / "root")
    cache = paths.quarantine_package("cache-plugin", "1.0.0")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(PAYLOAD)
    part = cache.with_suffix(".zip.part")
    part.write_bytes(PAYLOAD[:10])
    staging = paths.staging_dir("cache-plugin", "1.0.0", "abc123")
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "junk.txt").write_text("stale")

    _cleanup_stale_install_artifacts(paths)

    assert cache.is_file()  # verified cache survives restarts
    assert not part.exists()  # aborted download temp is cleaned
    assert not staging.exists()  # stale staging is cleaned

"""P1-4 global package-cache capacity governance: the quarantine zip cache
evicts oldest-first (mtime LRU, cross-plugin) under a global cap (default
4 GB, env-overridable). Never evicted: keep/active zips, recently-modified
zips (in-flight operations), non-zip files. Best-effort: never raises.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from mikazuki.plugin_marketplace.catalog import (
    _cache_max_bytes,
    MarketplaceCatalogService,
)
from mikazuki.plugin_marketplace.paths import MarketplacePaths
from mikazuki.plugin_marketplace.trust import TrustStore


def _service(tmp_path: Path) -> tuple[MarketplaceCatalogService, MarketplacePaths]:
    paths = MarketplacePaths(tmp_path / "root")
    service = MarketplaceCatalogService(paths=paths, trust=TrustStore({}))
    return service, paths


def _zip(paths: MarketplacePaths, plugin_id: str, version: str, size: int, *, age_seconds: float = 86400.0) -> Path:
    path = paths.quarantine_package(plugin_id, version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    past = time.time() - age_seconds
    os.utime(path, (past, past))
    return path


def test_no_eviction_when_under_cap(tmp_path: Path):
    service, paths = _service(tmp_path)
    a = _zip(paths, "alpha", "0.1.0", 100)
    b = _zip(paths, "beta", "0.2.0", 100)
    assert service.prune_global_package_cache(max_bytes=1000) == 0
    assert a.is_file() and b.is_file()


def test_evicts_oldest_first_across_plugins(tmp_path: Path):
    service, paths = _service(tmp_path)
    oldest = _zip(paths, "alpha", "0.1.0", 300, age_seconds=4 * 86400)
    middle = _zip(paths, "beta", "0.2.0", 300, age_seconds=2 * 86400)
    newest = _zip(paths, "gamma", "0.3.0", 300, age_seconds=1 * 86400)
    # Total 900B under a 600B cap: minimal eviction = the single oldest goes
    # (600B remains, exactly at the cap); the rest survive.
    freed = service.prune_global_package_cache(max_bytes=600)
    assert freed == 300
    assert not oldest.is_file()
    assert middle.is_file()
    assert newest.is_file()


def test_keep_set_is_protected_even_when_oldest(tmp_path: Path):
    service, paths = _service(tmp_path)
    keep_me = _zip(paths, "alpha", "0.1.0", 300, age_seconds=5 * 86400)
    other = _zip(paths, "beta", "0.2.0", 300, age_seconds=1 * 86400)
    freed = service.prune_global_package_cache({keep_me}, max_bytes=300)
    assert freed == 300
    assert keep_me.is_file()  # protected despite being the oldest
    assert not other.is_file()


def test_recently_modified_zip_is_protected(tmp_path: Path):
    service, paths = _service(tmp_path)
    old = _zip(paths, "alpha", "0.1.0", 300, age_seconds=10 * 86400)
    # Fresh zip (default mtime = now): even though it is the newest, the
    # point is the opposite — an OLD file inside the recent window...
    recent = _zip(paths, "beta", "0.2.0", 300, age_seconds=60)
    # Cap so that BOTH would need to go; the 60s-old one must survive.
    freed = service.prune_global_package_cache(max_bytes=100)
    assert freed == 300
    assert recent.is_file()  # in-flight protection window (300s)
    assert not old.is_file()


def test_only_oldest_evicted_until_cap_met(tmp_path: Path):
    service, paths = _service(tmp_path)
    files = [_zip(paths, f"plug{i:02d}", "0.1.0", 200, age_seconds=(10 - i) * 86400) for i in range(5)]
    # 1000B total, cap 600B: evict until 600B remain = exactly two files (400B).
    freed = service.prune_global_package_cache(max_bytes=600)
    assert freed == 400
    remaining = [p for p in files if p.is_file()]
    assert len(remaining) == 3
    # The three newest survive; the two oldest were evicted.
    assert all(p.is_file() for p in files[2:])
    assert not files[0].is_file() and not files[1].is_file()


def test_non_zip_files_are_never_touched(tmp_path: Path):
    service, paths = _service(tmp_path)
    zip_file = _zip(paths, "alpha", "0.1.0", 300, age_seconds=9 * 86400)
    stray_part = paths.quarantine_packages("alpha") / "0.2.0.zip.part"
    stray_part.write_bytes(b"y" * 500)
    freed = service.prune_global_package_cache(max_bytes=100)
    assert freed == 300
    assert not zip_file.is_file()
    assert stray_part.is_file()  # .part temps are out of scope (acquirer-owned)


def test_missing_quarantine_root_is_a_noop(tmp_path: Path):
    service, _paths = _service(tmp_path)
    assert service.prune_global_package_cache(max_bytes=100) == 0


def test_env_override_of_cap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_CACHE_MAX_BYTES", "12345")
    assert _cache_max_bytes() == 12345
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_CACHE_MAX_BYTES", "not-a-number")
    assert _cache_max_bytes() == 4 * 1024 * 1024 * 1024
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_CACHE_MAX_BYTES")
    assert _cache_max_bytes() == 4 * 1024 * 1024 * 1024


def test_env_cap_applied_by_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_CACHE_MAX_BYTES", "300")
    service, paths = _service(tmp_path)
    old = _zip(paths, "alpha", "0.1.0", 300, age_seconds=9 * 86400)
    new = _zip(paths, "beta", "0.2.0", 300, age_seconds=8 * 86400)
    # No max_bytes argument: the env cap (300B) drives the sweep.
    freed = service.prune_global_package_cache()
    assert freed == 300
    assert not old.is_file()
    assert new.is_file()


def test_prune_logs_freed_bytes(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    caplog.set_level("INFO", logger="mikazuki.plugin_marketplace.catalog")
    service, paths = _service(tmp_path)
    _zip(paths, "alpha", "0.1.0", 300, age_seconds=9 * 86400)
    service.prune_global_package_cache(max_bytes=100)
    assert any("pruned" in r.getMessage() and "300 bytes freed" in r.getMessage() for r in caplog.records)

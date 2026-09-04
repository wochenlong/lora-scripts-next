"""F3-1: HttpCatalogSource — the online release update channel.

Covers transport, the size cap, the offline fallback composition, the full
service refresh (signature-verified catalog becomes the cache), and the
env-driven wiring that prefers a live signed catalog over a bundled file.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from mikazuki.plugin_marketplace.api import _local_catalog_wiring, _marketplace_paths
from mikazuki.plugin_marketplace.catalog import (
    CatalogError,
    FallbackCatalogSource,
    FileCatalogSource,
    HttpCatalogSource,
    MarketplaceCatalogService,
)
from mikazuki.plugin_marketplace.models import MarketplaceCatalog, MarketplaceEntry
from mikazuki.plugin_marketplace.paths import MarketplacePaths
from mikazuki.plugin_marketplace.trust import TrustStore, canonical_catalog_payload

KEY_ID = "test-key-1"
PUBLISHER = "next-trainer-project"
KEY = hashlib.sha256(b"test-catalog-key").digest()


def _entry(version: str = "9.9.9") -> MarketplaceEntry:
    return MarketplaceEntry(
        id="next-trainer-pi-agent",
        name="Next Trainer Agent",
        publisher_id=PUBLISHER,
        latest_version=version,
        host_compatibility=">=2.9.2 <4.0.0",
        platforms=["win32-x64"],
        package_size=1,
        permissions_summary=[],
        license="MIT",
        package_url="https://plugins.next-trainer.example.com/p.zip",
        sha256="0" * 64,
        signature="1" * 64,
        signing_key_id=KEY_ID,
        published_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )


def _signed_catalog_bytes(version: str = "9.9.9", key: bytes = KEY) -> bytes:
    catalog = MarketplaceCatalog(
        schemaVersion=1,
        publisherId=PUBLISHER,
        signingKeyId=KEY_ID,
        generatedAt=datetime(2026, 8, 29, tzinfo=timezone.utc),
        entries=[_entry(version)],
        signature="0" * 64,
    )
    catalog.signature = hmac.new(key, canonical_catalog_payload(catalog), hashlib.sha256).hexdigest()
    return json.dumps(catalog.model_dump(by_alias=True, mode="json")).encode("utf-8")


def _trust_store(key: bytes = KEY) -> TrustStore:
    return TrustStore({KEY_ID: (PUBLISHER, key)})


class _Handler(BaseHTTPRequestHandler):
    payload = b"{}"
    status = 200
    raw_body = False

    def do_GET(self):  # noqa: N802
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *args):  # silence
        pass


@pytest.fixture
def server():
    handler = type("Bound", (_Handler,), {"payload": b"{}", "status": 200})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/catalog.json"
    try:
        yield srv, base
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def test_http_catalog_source_reads_served_bytes(server):
    srv, url = server
    srv.RequestHandlerClass.payload = _signed_catalog_bytes()
    assert HttpCatalogSource(url).read() == _signed_catalog_bytes()


def test_http_source_size_cap(server):
    srv, url = server
    srv.RequestHandlerClass.payload = b"x" * (HttpCatalogSource.max_response_bytes + 1)
    with pytest.raises(CatalogError) as exc:
        HttpCatalogSource(url).read()
    assert exc.value.code == "MARKETPLACE_CATALOG_TOO_LARGE"


def test_http_source_offline_is_catalog_error():
    # A port nothing listens on: transport failure becomes 503 OFFLINE, not a raw exception.
    src = HttpCatalogSource("http://127.0.0.1:1/catalog.json", timeout_seconds=2)
    with pytest.raises(CatalogError) as exc:
        src.read()
    assert exc.value.code == "MARKETPLACE_CATALOG_OFFLINE"


@pytest.mark.parametrize(
    "bad_url, reason",
    [
        ("https://user:pw@example.com/c.json", "credentials"),
        ("ftp://example.com/c.json", "scheme"),
        ("http://10.0.0.5/c.json", "plain-http non-loopback"),
    ],
)
def test_http_source_rejects_bad_urls(bad_url, reason):
    with pytest.raises(ValueError):
        HttpCatalogSource(bad_url)


def test_fallback_prefers_live_then_file(tmp_path):
    file_src = FileCatalogSource(tmp_path / "catalog.json")
    (tmp_path / "catalog.json").write_bytes(b"FILE")
    ok = type("Ok", (CatalogError,), {})
    # Live source fails -> file wins.
    dead = HttpCatalogSource("http://127.0.0.1:1/c.json", timeout_seconds=1)
    assert FallbackCatalogSource(dead, file_src).read() == b"FILE"
    assert FallbackCatalogSource(file_src, dead).read() == b"FILE"


def test_refresh_verifies_live_catalog_and_caches(server, tmp_path):
    srv, url = server
    srv.RequestHandlerClass.payload = _signed_catalog_bytes("9.9.9")
    paths = MarketplacePaths(tmp_path / "root")
    service = MarketplaceCatalogService(paths=paths, trust=_trust_store(), source=HttpCatalogSource(url))
    catalog = service.refresh()
    assert catalog.entries[0].latest_version == "9.9.9"
    # refresh wrote the verified catalog to the on-disk cache.
    assert paths.catalog_cache_file.is_file()


def test_refresh_rejects_unsigned_by_trusted_key(server, tmp_path):
    srv, url = server
    srv.RequestHandlerClass.payload = _signed_catalog_bytes(key=b"not-the-trusted-key")
    paths = MarketplacePaths(tmp_path / "root")
    service = MarketplaceCatalogService(paths=paths, trust=_trust_store(), source=HttpCatalogSource(url))
    with pytest.raises(CatalogError) as exc:
        service.refresh()
    assert exc.value.code == "MARKETPLACE_CATALOG_UNTRUSTED"
    # An untrusted catalog must never land in the cache.
    assert not paths.catalog_cache_file.exists()


# --- env-driven wiring -----------------------------------------------------

def _write_trust(path: Path) -> None:
    path.write_text(
        json.dumps({"keys": {KEY_ID: {"publisherId": PUBLISHER, "keyHex": KEY.hex()}}, "revokedKeys": []}),
        encoding="utf-8",
    )


def test_catalog_url_env_composes_fallback_over_file(tmp_path, monkeypatch):
    trust = tmp_path / "trust.json"
    _write_trust(trust)
    cat = tmp_path / "catalog.json"
    cat.write_bytes(b"{}")
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_TRUST", str(trust))
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_CATALOG", str(cat))
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_CATALOG_URL", "https://plugins.example.com/catalog.json")
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_PACKAGE_ROOT", raising=False)
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_PACKAGE_MIRROR", raising=False)
    _trust, _trust_seq, source, _acquirer = _local_catalog_wiring(_marketplace_paths())
    assert isinstance(source, FallbackCatalogSource)
    kinds = [type(s).__name__ for s in source.sources]
    assert kinds == ["HttpCatalogSource", "FileCatalogSource"]  # live first, file as offline fallback


def test_catalog_url_only_still_needs_trust(tmp_path, monkeypatch):
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_TRUST", raising=False)
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_CATALOG", raising=False)
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_PACKAGE_ROOT", raising=False)
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_PACKAGE_MIRROR", raising=False)
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_CATALOG_URL", "https://plugins.example.com/catalog.json")
    monkeypatch.chdir(tmp_path)
    trust, _trust_seq, source, acquirer = _local_catalog_wiring(_marketplace_paths())
    # URL without a trust root is a partial env -> fail closed.
    assert source is None and acquirer is None


def test_catalog_url_env_wires_http_acquirer(tmp_path, monkeypatch):
    # Regression (user-reported): with a trusted live channel configured but no
    # local package root, install-after-uninstall failed with
    # MARKETPLACE_PACKAGE_ACQUISITION_UNAVAILABLE while the cached catalog kept
    # showing an installable listing. The catalog pins each package's https URL
    # + size + sha256, so HTTP acquisition must be wired automatically.
    trust = tmp_path / "trust.json"
    _write_trust(trust)
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_TRUST", str(trust))
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_CATALOG_URL", "https://plugins.example.com/catalog.json")
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_CATALOG", raising=False)
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_PACKAGE_ROOT", raising=False)
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_PACKAGE_MIRROR", raising=False)
    monkeypatch.chdir(tmp_path)
    _trust, _trust_seq, source, acquirer = _local_catalog_wiring(_marketplace_paths())
    assert source is not None
    from mikazuki.plugin_marketplace.catalog import HttpPackageAcquirer, UnavailablePackageAcquirer
    assert isinstance(acquirer, HttpPackageAcquirer)
    assert not isinstance(acquirer, UnavailablePackageAcquirer)


def test_bundled_tier_without_packages_dir_stays_unavailable(tmp_path, monkeypatch):
    # Counter-contract: the offline one-click bundle must NOT gain silent
    # network acquisition — only an explicit env channel opts into HTTP.
    bundled = tmp_path / "plugin-marketplace"
    (bundled).mkdir()
    (bundled / "catalog.json").write_bytes(b"{}")
    _write_trust(bundled / "trust.json")
    for var in ("MIKAZUKI_MARKETPLACE_CATALOG", "MIKAZUKI_MARKETPLACE_TRUST",
                "MIKAZUKI_MARKETPLACE_CATALOG_URL", "MIKAZUKI_MARKETPLACE_PACKAGE_ROOT",
                "MIKAZUKI_MARKETPLACE_PACKAGE_MIRROR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    _trust, _trust_seq, source, acquirer = _local_catalog_wiring(_marketplace_paths())
    assert source is not None  # bundled catalog is still listed
    from mikazuki.plugin_marketplace.catalog import UnavailablePackageAcquirer
    assert isinstance(acquirer, UnavailablePackageAcquirer)


def test_catalog_url_invalid_fails_closed(tmp_path, monkeypatch):
    trust = tmp_path / "trust.json"
    _write_trust(trust)
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_TRUST", str(trust))
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_CATALOG", raising=False)
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_PACKAGE_ROOT", raising=False)
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_PACKAGE_MIRROR", raising=False)
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_CATALOG_URL", "http://10.0.0.5/catalog.json")
    monkeypatch.chdir(tmp_path)
    _trust, _trust_seq, source, acquirer = _local_catalog_wiring(_marketplace_paths())
    assert source is None and acquirer is None

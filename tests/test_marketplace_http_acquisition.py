"""Stage 2 (B1) acquisition tests: HTTP download, mirror, retries, cancel.

The catalog model pins HTTPS public URLs, so these tests never point a catalog
entry at the local test server. Instead they use the mirror base URL rewrite
(HttpPackageAcquirer + MIKAZUKI_MARKETPLACE_PACKAGE_MIRROR semantics) to serve
the dev-placeholder URL from a loopback HTTP file server — exactly the release
dry-run path.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from mikazuki.plugin_marketplace.catalog import (
    CatalogError,
    HttpPackageAcquirer,
    LocalFirstPackageAcquirer,
    LocalPackageAcquirer,
)
from mikazuki.plugin_marketplace.models import MarketplaceEntry
from mikazuki.plugin_marketplace.trust import canonical_entry_payload


KEY = b"test-acquisition-key"
DEV_URL = "https://plugins.next-trainer.local/packages/pkg.zip"
FLAKY_URL = "https://plugins.next-trainer.local/flaky/pkg.zip"
SLOW_URL = "https://plugins.next-trainer.local/slow/pkg.zip"
MISSING_URL = "https://plugins.next-trainer.local/packages/does-not-exist.zip"


class _ServerState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.hits: dict[str, int] = {}

    def hit(self, path: str) -> int:
        with self.lock:
            self.hits[path] = self.hits.get(path, 0) + 1
            return self.hits[path]


def _build_entry(payload: bytes, *, url: str, size_override: int | None = None, sha_override: str | None = None) -> MarketplaceEntry:
    digest = hashlib.sha256(payload).hexdigest()
    value = {
        "id": "sample-plugin",
        "name": "Sample",
        "publisher_id": "approved-publisher-id",
        "latest_version": "1.0.0",
        "channel": "stable",
        "host_compatibility": ">=2.9.2 <3.0.0",
        "platforms": ["win32-x64"],
        "package_size": len(payload),
        "permissions_summary": [],
        "license": "MIT",
        "package_url": url,
        "sha256": digest,
        "signature": "",
        "signing_key_id": "test-key",
        "published_at": "2026-08-29T00:00:00Z",
    }
    if size_override is not None:
        value["package_size"] = size_override
    if sha_override is not None:
        value["sha256"] = sha_override
    unsigned = MarketplaceEntry.model_validate(value)
    value["signature"] = hmac.new(KEY, canonical_entry_payload(unsigned), hashlib.sha256).hexdigest()
    return MarketplaceEntry.model_validate(value)


@pytest.fixture()
def http_server(tmp_path: Path):
    serve_dir = tmp_path / "serve"
    (serve_dir / "packages").mkdir(parents=True)
    payload = (b"plugin-package-bytes" * 20_000) + b"tail"
    (serve_dir / "packages" / "pkg.zip").write_bytes(payload)
    state = _ServerState()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # silence
            pass

        def _serve_file(self, file: Path) -> None:
            data = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path
            count = state.hit(path)
            if path.startswith("/missing/") or path.endswith("does-not-exist.zip"):
                self.send_response(404)
                self.end_headers()
                return
            if path.startswith("/flaky/"):
                if count <= 2:
                    self.send_response(503)
                    self.end_headers()
                    return
                self._serve_file(serve_dir / "packages" / "pkg.zip")
                return
            if path.startswith("/slow/"):
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                try:
                    chunk = 8 * 1024
                    for offset in range(0, len(payload), chunk):
                        time.sleep(0.02)
                        self.wfile.write(payload[offset : offset + chunk])
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
                return
            if path.startswith("/packages/"):
                file = serve_dir / path[1:]
                if file.is_file():
                    self._serve_file(file)
                    return
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(404)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "base_url": f"http://127.0.0.1:{server.server_address[1]}",
            "payload": payload,
            "state": state,
        }
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_acquirer_downloads_with_progress_and_verifies(http_server, tmp_path: Path):
    acquirer = HttpPackageAcquirer(http_server["base_url"])
    entry = _build_entry(http_server["payload"], url=DEV_URL)
    destination = tmp_path / "quarantine" / "pkg.zip"
    samples: list[tuple[int, int]] = []
    result = acquirer.acquire(entry, destination, "win32-x64", on_progress=lambda c, t: samples.append((c, t)))
    assert result == destination
    assert destination.read_bytes() == http_server["payload"]
    total = len(http_server["payload"])
    assert samples[0] == (0, total)
    assert samples[-1] == (total, total)
    currents = [sample[0] for sample in samples]
    assert currents == sorted(currents)
    assert all(sample[1] == total for sample in samples)


def test_http_acquirer_rejects_checksum_mismatch(http_server, tmp_path: Path):
    acquirer = HttpPackageAcquirer(http_server["base_url"])
    entry = _build_entry(http_server["payload"], url=DEV_URL, sha_override="0" * 64)
    destination = tmp_path / "pkg.zip"
    with pytest.raises(CatalogError) as excinfo:
        acquirer.acquire(entry, destination, "win32-x64")
    assert excinfo.value.code == "MARKETPLACE_PACKAGE_CHECKSUM_MISMATCH"
    assert not destination.exists()
    assert not destination.with_suffix(".zip.part").exists()


def test_http_acquirer_rejects_size_mismatch(http_server, tmp_path: Path):
    acquirer = HttpPackageAcquirer(http_server["base_url"])
    entry = _build_entry(http_server["payload"], url=DEV_URL, size_override=len(http_server["payload"]) + 1)
    destination = tmp_path / "pkg.zip"
    with pytest.raises(CatalogError) as excinfo:
        acquirer.acquire(entry, destination, "win32-x64")
    assert excinfo.value.code == "MARKETPLACE_PACKAGE_SIZE_MISMATCH"
    assert not destination.exists()


def test_http_acquirer_404_is_not_retried(http_server, tmp_path: Path):
    acquirer = HttpPackageAcquirer(http_server["base_url"])
    entry = _build_entry(http_server["payload"], url=MISSING_URL)
    destination = tmp_path / "pkg.zip"
    with pytest.raises(CatalogError) as excinfo:
        acquirer.acquire(entry, destination, "win32-x64")
    assert excinfo.value.code == "MARKETPLACE_PACKAGE_UNAVAILABLE"
    assert excinfo.value.status_code == 404
    assert http_server["state"].hits["/packages/does-not-exist.zip"] == 1


def test_http_acquirer_retries_transient_503(http_server, tmp_path: Path):
    acquirer = HttpPackageAcquirer(http_server["base_url"])
    entry = _build_entry(http_server["payload"], url=FLAKY_URL)
    destination = tmp_path / "pkg.zip"
    result = acquirer.acquire(entry, destination, "win32-x64")
    assert destination.read_bytes() == http_server["payload"]
    assert http_server["state"].hits["/flaky/pkg.zip"] == 3


def test_http_acquirer_cancel_mid_download_cleans_part(http_server, tmp_path: Path):
    acquirer = HttpPackageAcquirer(http_server["base_url"])
    entry = _build_entry(http_server["payload"], url=SLOW_URL)
    destination = tmp_path / "pkg.zip"
    cancelled = threading.Event()

    def flag() -> bool:
        return cancelled.is_set()

    timer = threading.Timer(0.2, cancelled.set)
    timer.start()
    try:
        with pytest.raises(CatalogError) as excinfo:
            acquirer.acquire(entry, destination, "win32-x64", is_cancelled=flag)
        assert excinfo.value.code == "MARKETPLACE_OPERATION_CANCELLED"
    finally:
        timer.cancel()
    assert not destination.exists()
    assert not destination.with_suffix(".zip.part").exists()


def test_local_first_prefers_local_map(http_server, tmp_path: Path):
    local_file = tmp_path / "local" / "pkg.zip"
    local_file.parent.mkdir()
    local_file.write_bytes(http_server["payload"])
    combiner = LocalFirstPackageAcquirer(
        LocalPackageAcquirer({DEV_URL: local_file}),
        HttpPackageAcquirer(http_server["base_url"]),
    )
    entry = _build_entry(http_server["payload"], url=DEV_URL)
    destination = tmp_path / "quarantine" / "pkg.zip"
    result = combiner.acquire(entry, destination, "win32-x64")
    assert result.read_bytes() == http_server["payload"]
    # The local map served it: the HTTP origin was never contacted.
    assert http_server["state"].hits.get("/packages/pkg.zip") is None


def test_local_first_falls_through_to_http(http_server, tmp_path: Path):
    combiner = LocalFirstPackageAcquirer(
        LocalPackageAcquirer({}),
        HttpPackageAcquirer(http_server["base_url"]),
    )
    entry = _build_entry(http_server["payload"], url=DEV_URL)
    destination = tmp_path / "pkg.zip"
    result = combiner.acquire(entry, destination, "win32-x64")
    assert result.read_bytes() == http_server["payload"]
    assert http_server["state"].hits["/packages/pkg.zip"] == 1


def test_local_first_local_integrity_failure_is_not_masked(http_server, tmp_path: Path):
    local_file = tmp_path / "local" / "pkg.zip"
    local_file.parent.mkdir()
    local_file.write_bytes(http_server["payload"] + b"extra")
    combiner = LocalFirstPackageAcquirer(
        LocalPackageAcquirer({DEV_URL: local_file}),
        HttpPackageAcquirer(http_server["base_url"]),
    )
    entry = _build_entry(http_server["payload"], url=DEV_URL)
    destination = tmp_path / "pkg.zip"
    with pytest.raises(CatalogError) as excinfo:
        combiner.acquire(entry, destination, "win32-x64")
    assert excinfo.value.code == "MARKETPLACE_PACKAGE_SIZE_MISMATCH"
    assert http_server["state"].hits.get("/packages/pkg.zip") is None


def test_mirror_policy_allows_only_loopback_plain_http():
    with pytest.raises(ValueError):
        HttpPackageAcquirer("http://8.8.8.8/mirror")
    with pytest.raises(ValueError):
        HttpPackageAcquirer("ftp://127.0.0.1/mirror")
    # These are accepted (validation happens, fetching is not attempted).
    assert HttpPackageAcquirer("http://127.0.0.1:8000")._mirror == "http://127.0.0.1:8000"
    assert HttpPackageAcquirer("https://plugins.example.com/mirror")._mirror == "https://plugins.example.com/mirror"
    assert HttpPackageAcquirer(None)._mirror is None

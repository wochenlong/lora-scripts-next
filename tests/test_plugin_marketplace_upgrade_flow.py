"""F3-2: the plugin upgrade storyline over the HTTP acquisition path.

Manager-level update/rollback semantics are already pinned in
test_plugin_marketplace.py; this file nails the RELEASE SHAPE end to end:
fixture zips served from a loopback mirror, catalog-pinned https URLs,
acquisition through HttpPackageAcquirer, install as upgrade (side-by-side +
atomic switch), plugin data-root sovereignty across versions, and rollback.
"""
from __future__ import annotations

import hashlib
import hmac
import http.server
import threading
from pathlib import Path

import pytest

from mikazuki.plugin_marketplace.catalog import CatalogError, HttpPackageAcquirer
from mikazuki.plugin_marketplace.models import MarketplaceEntry
from mikazuki.plugin_marketplace.paths import MarketplacePaths
from mikazuki.plugin_marketplace.trust import canonical_entry_payload
from test_plugin_marketplace import FakeRuntime, build_package, manager_for, signed_entry

PLUGIN_ID = "next-trainer-pi-agent"
PERMISSIONS = {"model-provider", "training-config"}


class _PackagesHandler(http.server.BaseHTTPRequestHandler):
    root = Path(".")

    def do_GET(self):  # noqa: N802
        member = (self.root / Path(self.path).name).resolve()
        if member.parent != self.root.resolve() or not member.is_file():
            self.send_error(404)
            return
        body = member.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence
        pass


@pytest.fixture
def marketplace(tmp_path):
    """Loopback package mirror + acquisition stack over two release versions."""
    packages = tmp_path / "packages"
    packages.mkdir()
    v3 = build_package(packages, version="0.3.3").rename(packages / "agent-0.3.3.zip")
    v4 = build_package(packages, version="0.3.4").rename(packages / "agent-0.3.4.zip")
    handler = type("Bound", (_PackagesHandler,), {"root": packages})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    mirror = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield {
            "packages": {"0.3.3": v3, "0.3.4": v4},
            "acquirer": HttpPackageAcquirer(mirror),
        }
    finally:
        server.shutdown()
        server.server_close()


def _entry_for(package: Path, key: bytes, version: str) -> MarketplaceEntry:
    # Catalog URLs stay https per model rules; the mirror rewrites the path onto
    # loopback exactly like the documented release dry-run.
    return signed_entry(
        package,
        key,
        version=version,
        package_url=f"https://plugins.next-trainer.local/packages/agent-{version}.zip",
    )


def test_upgrade_over_http_switches_runtime_then_rollback_preserves_data_root(marketplace, tmp_path):
    root = tmp_path / "marketplace-root"
    runtime = FakeRuntime()
    manager, key = manager_for(root, runtime=runtime)
    paths: MarketplacePaths = manager.paths
    quarantine = paths.cache_dir(PLUGIN_ID)

    # 1. Fresh install of 0.3.3 acquired over HTTP, then enabled.
    entry3 = _entry_for(marketplace["packages"]["0.3.3"], key, "0.3.3")
    acquired3 = marketplace["acquirer"].acquire(entry3, quarantine / "agent-0.3.3.zip", "win32-x64")
    manager.install(entry3, acquired3)
    manager.enable(PLUGIN_ID, PERMISSIONS)
    assert runtime.starts == ["0.3.3"]

    # 2. First-launch seeding into the plugin data root (the user's sovereign tree).
    data_root = paths.user_data_dir(PLUGIN_ID)
    knowledge = data_root / "knowledge" / "learning-rate.md"
    knowledge.parent.mkdir(parents=True, exist_ok=True)
    knowledge.write_text("# user curated\n", encoding="utf-8")
    user_note = data_root / "knowledge" / "my-own-notes.md"
    user_note.write_text("# mine\n", encoding="utf-8")

    # 3. A newer catalog revision publishes 0.3.4; installing it upgrades side-by-side.
    entry4 = _entry_for(marketplace["packages"]["0.3.4"], key, "0.3.4")
    acquired4 = marketplace["acquirer"].acquire(entry4, quarantine / "agent-0.3.4.zip", "win32-x64")
    upgraded = manager.install(entry4, acquired4)

    assert upgraded.active_version == "0.3.4"
    assert upgraded.previous_version == "0.3.3"
    assert upgraded.enabled is True and upgraded.state == "enabled"
    assert paths.version_dir(PLUGIN_ID, "0.3.3").is_dir() and paths.version_dir(PLUGIN_ID, "0.3.4").is_dir()
    assert runtime.starts == ["0.3.3", "0.3.4"]  # old stopped, new started
    assert runtime.running == (PLUGIN_ID, "0.3.4")

    # 4. The data root is untouched across the upgrade (host never rewrites it).
    assert knowledge.read_text(encoding="utf-8") == "# user curated\n"
    assert user_note.is_file()

    # 5. Rollback returns the active pointer and restarts the old runtime.
    rolled = manager.rollback(PLUGIN_ID)
    assert rolled.active_version == "0.3.3"
    assert rolled.previous_version == "0.3.4"
    assert runtime.starts == ["0.3.3", "0.3.4", "0.3.3"]
    assert runtime.running == (PLUGIN_ID, "0.3.3")
    assert knowledge.is_file() and user_note.is_file()


def test_tampered_package_in_transit_refused_without_touching_active_version(marketplace, tmp_path):
    root = tmp_path / "marketplace-root"
    manager, key = manager_for(root)
    paths = manager.paths
    entry3 = _entry_for(marketplace["packages"]["0.3.3"], key, "0.3.3")
    manager.install(entry3, marketplace["acquirer"].acquire(entry3, paths.cache_dir(PLUGIN_ID) / "a.zip", "win32-x64"))

    # The catalog pinned the ORIGINAL bytes; a hostile path now serves a mutated
    # body under the same URL (one flipped byte, same size).
    victim = marketplace["packages"]["0.3.4"]
    original = victim.read_bytes()
    entry4 = _entry_for(victim, key, "0.3.4")
    victim.write_bytes(original[:-1] + bytes([original[-1] ^ 0xFF]))

    with pytest.raises(CatalogError) as exc:
        marketplace["acquirer"].acquire(entry4, paths.cache_dir(PLUGIN_ID) / "agent-0.3.4.zip", "win32-x64")
    assert "checksum" in str(exc.value).lower() or "sha" in str(exc.value).lower()
    # No half-written upgrade survives a failed acquisition.
    assert not (paths.cache_dir(PLUGIN_ID) / "agent-0.3.4.zip").exists()
    assert not (paths.cache_dir(PLUGIN_ID) / "agent-0.3.4.zip.part").exists()
    assert manager.status(PLUGIN_ID).active_version == "0.3.3"


def test_entry_with_sha_mismatch_is_refused_before_install(marketplace, tmp_path):
    # Defense in depth: even if acquisition were bypassed, trust.verify rejects a
    # package whose digest no longer matches the signed pin (manager raises).
    root = tmp_path / "marketplace-root"
    manager, key = manager_for(root)
    victim = marketplace["packages"]["0.3.4"]
    entry4 = _entry_for(victim, key, "0.3.4")
    victim.write_bytes(victim.read_bytes() + b"tamper")
    with pytest.raises(Exception) as exc:
        manager.install(entry4, victim)
    assert "sha256" in str(exc.value) or "size" in str(exc.value)

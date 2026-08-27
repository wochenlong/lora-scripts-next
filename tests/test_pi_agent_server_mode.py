"""Goal v9 / CR-011 — host-side server-mode integration tests (S5).

Covers the minimal host changes that let the verbatim pi-web embed report its
live loopback URL through the runtime contract:

- READY `uiUrl`/`childPid` capture + loopback validation
- `RuntimeSnapshot.ui_url` / `PluginStatus.runtime_ui_url` projection
- floating panel `mode: "server"` vs `mode: "static"` extension projection
- stop() best-effort grandchild-tree removal via the recorded child PID
- env-gated local catalog/trust wiring against the real dist-marketplace
  artifacts (HMAC signatures included)
- raised PackageLimits defaults still bound the shipped pi-web package
"""
from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

from mikazuki.plugin_host.runtime import (
    ExecutablePluginRuntime,
    RuntimeSnapshot,
    _ProcessHandle,
    _is_loopback_ui_url,
)
from mikazuki.plugin_marketplace.api import _local_catalog_wiring
from mikazuki.plugin_marketplace.catalog import (
    FileCatalogSource,
    LocalPackageAcquirer,
    MarketplaceCatalogService,
)
from mikazuki.plugin_marketplace.manager import MarketplaceManager
from mikazuki.plugin_marketplace.models import MarketplaceEntry
from mikazuki.plugin_marketplace.package import PackageLimits, _raw_path, extract_package, remove_tree
from mikazuki.plugin_marketplace.paths import MarketplacePaths
from mikazuki.plugin_marketplace.store import MarketplaceStore
from mikazuki.plugin_marketplace.trust import TrustStore, canonical_entry_payload, load_trust_root


HOST_VERSION = "2.9.2"
DIST_MARKETPLACE = Path(__file__).resolve().parents[1] / "plugin-packages" / "next-trainer-pi-agent" / "dist-marketplace"


# ---------------------------------------------------------------------------
# READY extras: loopback validation
# ---------------------------------------------------------------------------


def test_loopback_ui_url_validator():
    assert _is_loopback_ui_url("http://127.0.0.1:51234")
    assert _is_loopback_ui_url("http://127.0.0.1:51234/")
    assert not _is_loopback_ui_url("http://localhost:51234")
    assert not _is_loopback_ui_url("https://127.0.0.1:51234")
    assert not _is_loopback_ui_url("http://127.0.0.1")
    assert not _is_loopback_ui_url("http://user:pass@127.0.0.1:51234/")
    assert not _is_loopback_ui_url("ftp://127.0.0.1:51234")
    assert not _is_loopback_ui_url("not a url")


# ---------------------------------------------------------------------------
# Projection: RuntimeSnapshot.ui_url -> PluginStatus -> extensions
# ---------------------------------------------------------------------------


def _manifest_dict(*, settings: bool = True) -> dict:
    return {
        "id": "next-trainer-pi-agent",
        "publisher": "approved-publisher-id",
        "version": "0.2.0",
        "protocolVersion": "1",
        "hostCompatibility": ">=2.9.2 <3.0.0",
        "platforms": ["win32-x64"],
        "runtime": {"kind": "executable", "entrypoint": "bin/next-trainer-pi-agent.exe"},
        "ui": {
            "entrypoint": "ui/index.html",
            **({"settingsEntrypoint": "ui/settings.html"} if settings else {}),
            "extensionApi": "1",
            "placements": ["floating-panel"],
        },
        "bridge": {"requests": [], "streams": []},
        "capabilities": ["server-ui"],
        "permissions": [],
        "package": {"sha256": "catalog-owned", "signature": "catalog-owned", "sbom": "sbom.cdx.json"},
        "installHooks": [],
    }


def _build_package(root: Path) -> Path:
    package = root / "agent-0.2.0.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(_manifest_dict()))
        archive.writestr("bin/next-trainer-pi-agent.exe", b"mock executable")
        archive.writestr("ui/index.html", "<html></html>")
        archive.writestr("ui/settings.html", "<html></html>")
        archive.writestr("sbom.cdx.json", '{"bomFormat":"CycloneDX"}')
        archive.writestr("LICENSE", "MIT")
    return package


def _signed_entry(package: Path, key: bytes) -> MarketplaceEntry:
    data = {
        "id": "next-trainer-pi-agent",
        "name": "Next Trainer Pi Agent",
        "publisher_id": "approved-publisher-id",
        "latest_version": "0.2.0",
        "channel": "stable",
        "host_compatibility": ">=2.9.2 <3.0.0",
        "platforms": ["win32-x64"],
        "package_size": package.stat().st_size,
        "permissions_summary": [],
        "license": "MIT",
        "package_url": "https://market.invalid/plugins/agent-0.2.0.zip",
        "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "signing_key_id": "test-key",
        "published_at": "2026-08-28T00:00:00Z",
        "signature": "",
    }
    entry = MarketplaceEntry.model_validate(data)
    data["signature"] = hmac.new(key, canonical_entry_payload(entry), hashlib.sha256).hexdigest()
    return MarketplaceEntry.model_validate(data)


class FakeRuntime:
    """Duck-typed PluginRuntimeController mirroring the real contract.

    Reports the ui_url its (simulated) READY line carried, so the
    snapshot -> status -> extension projection path is exercised without a
    real executable (the real process path is covered by the S3 launcher
    contract test and the existing runtime wire-contract tests).
    """

    def __init__(self, *, ui_url: str | None = None) -> None:
        self.ui_url = ui_url
        self.running: tuple[str, str] | None = None

    def start(self, manifest, _package_root: Path, _data_root: Path) -> RuntimeSnapshot:
        self.running = (manifest.id, manifest.version)
        return RuntimeSnapshot(
            state="running",
            version=manifest.version,
            pid=321,
            protocol_version="1",
            ui_url=self.ui_url,
        )

    def stop(self, plugin_id: str) -> None:
        if self.running is not None and self.running[0] == plugin_id:
            self.running = None

    def status(self, plugin_id: str) -> RuntimeSnapshot:
        if self.running is None or self.running[0] != plugin_id:
            return RuntimeSnapshot(state="stopped")
        return RuntimeSnapshot(
            state="running",
            version=self.running[1],
            pid=321,
            protocol_version="1",
            ui_url=self.ui_url,
        )


def _manager_with_runtime(root: Path, runtime: FakeRuntime) -> MarketplaceManager:
    key = b"stage-1-mock-signing-key"
    paths = MarketplacePaths(root)
    manager = MarketplaceManager(
        paths=paths,
        store=MarketplaceStore(paths.registry_file),
        trust=TrustStore({"test-key": ("approved-publisher-id", key)}),
        host_version=HOST_VERSION,
        platform="win32-x64",
        runtime=runtime,
    )
    package = _build_package(root)
    manager.install(_signed_entry(package, key), package)
    manager.enable("next-trainer-pi-agent", set())
    return manager


def test_server_mode_projection_uses_live_ui_url():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        runtime = FakeRuntime(ui_url="http://127.0.0.1:45999")
        manager = _manager_with_runtime(root, runtime)

        status = manager.status("next-trainer-pi-agent")
        assert status.runtime_state == "running"
        assert status.runtime_ui_url == "http://127.0.0.1:45999"

        extensions = manager.enabled_extensions()
        assert len(extensions) == 1
        panel = extensions[0]["ui"]["floatingPanel"]
        assert panel == {"mode": "server", "entryUrl": "http://127.0.0.1:45999"}
        assert extensions[0]["capabilities"] == []


def test_static_mode_projection_without_live_ui_url():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        runtime = FakeRuntime(ui_url=None)
        manager = _manager_with_runtime(root, runtime)

        status = manager.status("next-trainer-pi-agent")
        assert status.runtime_ui_url is None

        extensions = manager.enabled_extensions()
        panel = extensions[0]["ui"]["floatingPanel"]
        assert panel["mode"] == "static"
        assert panel["entryUrl"] == "/api/plugin-host/ui/next-trainer-pi-agent/0.2.0/index.html"


def test_stopped_runtime_does_not_leak_stale_ui_url():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        runtime = FakeRuntime(ui_url="http://127.0.0.1:45999")
        manager = _manager_with_runtime(root, runtime)
        manager.disable("next-trainer-pi-agent")
        status = manager.status("next-trainer-pi-agent")
        assert status.runtime_ui_url is None
        assert manager.enabled_extensions() == []


# ---------------------------------------------------------------------------
# stop(): best-effort grandchild tree removal
# ---------------------------------------------------------------------------


def test_stop_removes_recorded_child_tree():
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert child.pid
    try:

        class Process:
            @staticmethod
            def poll():
                return 0  # already terminated; _terminate must skip it

        runtime = ExecutablePluginRuntime()
        handle = _ProcessHandle(
            process=Process(),
            version="0.2.0",
            protocol_version="1",
            port=1,
            token="sidecar-secret-token-sidecar-secret",
            host_tool_token="host-tool-secret-host-tool-secret",
            child_pid=child.pid,
        )
        runtime._kill_child_tree(handle)
        child.wait(timeout=10)
        assert child.poll() is not None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_stop_without_child_pid_is_a_noop():
    class Process:
        @staticmethod
        def poll():
            return 0

    runtime = ExecutablePluginRuntime()
    handle = _ProcessHandle(
        process=Process(),
        version="0.2.0",
        protocol_version="1",
        port=1,
        token="sidecar-secret-token-sidecar-secret",
        host_tool_token="host-tool-secret-host-tool-secret",
    )
    runtime._kill_child_tree(handle)  # must not raise


# ---------------------------------------------------------------------------
# Env-gated local catalog/trust wiring against the real S4 artifacts
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (DIST_MARKETPLACE / "catalog.json").is_file(),
    reason="dist-marketplace artifacts have not been built (run scripts/build-pi-web-package.py)",
)
def test_local_catalog_wiring_against_dist_artifacts(monkeypatch):
    trust_path = DIST_MARKETPLACE / "trust.json"
    catalog_path = DIST_MARKETPLACE / "catalog.json"
    package_root = DIST_MARKETPLACE / "packages"
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_TRUST", str(trust_path))
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_CATALOG", str(catalog_path))
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_PACKAGE_ROOT", str(package_root))

    trust, source, acquirer = _local_catalog_wiring()
    assert isinstance(source, FileCatalogSource)
    assert isinstance(acquirer, LocalPackageAcquirer)

    # The trust root loads the dev key with its publisher identity.
    keys = getattr(trust, "_keys")
    assert "dev-local-signing" in keys
    assert keys["dev-local-signing"][0] == "next-trainer-project"

    # The catalog verifies against the HMAC test signatures and lists 0.2.0.
    service = MarketplaceCatalogService(
        paths=MarketplacePaths(Path(tempfile.mkdtemp())),
        trust=trust,
        source=source,
        acquirer=acquirer,
    )
    catalog = service.refresh()
    entry = service.entry("next-trainer-pi-agent")
    assert entry.latest_version == "0.2.0"
    assert entry.permissions_summary == []

    # The acquirer maps the HTTPS package URL to the local zip and the real
    # signature verifies against the real bytes.
    zip_path = package_root / f"{entry.id}-0.2.0-win32-x64.zip"
    assert zip_path.is_file()
    acquired = service.acquire(entry)
    try:
        trust.verify(entry, acquired)
    finally:
        acquired.unlink(missing_ok=True)


@pytest.mark.skipif(
    not (DIST_MARKETPLACE / "trust.json").is_file(),
    reason="dist-marketplace artifacts have not been built",
)
def test_local_catalog_wiring_fails_closed_without_env(monkeypatch):
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_TRUST", raising=False)
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_CATALOG", raising=False)
    monkeypatch.delenv("MIKAZUKI_MARKETPLACE_PACKAGE_ROOT", raising=False)
    trust, source, acquirer = _local_catalog_wiring()
    assert not getattr(trust, "_keys")
    assert source is None
    assert acquirer is None


def test_load_trust_root_rejects_invalid_shapes(tmp_path):
    good = tmp_path / "trust.json"
    good.write_text(
        json.dumps(
            {
                "keys": {
                    "k1": {"publisherId": "pub", "keyHex": "a" * 64},
                },
                "revokedKeys": [],
            }
        ),
        encoding="utf-8",
    )
    store = load_trust_root(good)
    assert store._keys["k1"][0] == "pub"
    assert store._keys["k1"][1] == bytes.fromhex("a" * 64)

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"keys": {"k1": {"publisherId": "pub", "keyHex": "zz"}}}), encoding="utf-8")
    with pytest.raises(Exception):
        load_trust_root(bad)


# ---------------------------------------------------------------------------
# PackageLimits defaults fit the shipped pi-web package
# ---------------------------------------------------------------------------


def test_package_limits_defaults_fit_pi_web_package():
    # Measured S4 build: 305,209,431 B zip, 1,315,626,627 B unpacked, 34,541 files.
    limits = PackageLimits()
    assert limits.max_package_bytes >= 305_209_431
    assert limits.max_unpacked_bytes >= 1_315_626_627
    assert limits.max_files >= 34_541
    # ...while still bounding pathological packages.
    assert limits.max_package_bytes <= 1024 * 1024 * 1024
    assert limits.max_unpacked_bytes <= 8 * 1024 * 1024 * 1024
    assert limits.max_files <= 100_000


def test_runtime_snapshot_carries_ui_url():
    snapshot = RuntimeSnapshot(state="running", version="0.2.0", ui_url="http://127.0.0.1:45999")
    assert snapshot.ui_url == "http://127.0.0.1:45999"
    assert RuntimeSnapshot(state="stopped").ui_url is None


# ---------------------------------------------------------------------------
# MAX_PATH-safe extraction/removal (deep vendored-SDK trees)
# ---------------------------------------------------------------------------


def test_extract_and_remove_package_survives_max_path_depth(tmp_path):
    """Vendored pi-web SDKs produce member paths beyond the 260-character
    Win32 limit; extraction and cleanup must still reach them on Windows
    (plain pathlib/shutil operations fail there with FileNotFoundError)."""
    deep = "/".join(f"dir{'x' * 20}{i}" for i in range(10)) + "/deep-file.js"
    package = tmp_path / "deep.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(deep, "console.log(1)")
        archive.writestr("shallow.txt", "shallow")
    with zipfile.ZipFile(package) as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]

    target = tmp_path / "out"
    extract_package(package, target, members)
    # Read back through the same raw-path access the fix provides (a plain
    # Path read would itself hit MAX_PATH on Windows for this depth).
    deep_file = _raw_path(target / Path(*deep.split("/")))
    assert deep_file.read_text(encoding="utf-8") == "console.log(1)"
    assert (target / "shallow.txt").read_text(encoding="utf-8") == "shallow"

    # Cleanup must reach the same depth (plain shutil.rmtree leaves the
    # deep tail behind on Windows), and stay idempotent afterwards.
    remove_tree(target)
    assert not target.exists()
    remove_tree(target)
    assert not target.exists()

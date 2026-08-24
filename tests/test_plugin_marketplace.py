from __future__ import annotations

import asyncio
import hashlib
import hmac
import http.server
import json
import tempfile
import threading
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from mikazuki.plugin_marketplace.manager import MarketplaceManager
from mikazuki.plugin_marketplace.models import MarketplaceEntry, PluginManifest
from mikazuki.plugin_marketplace.package import PackageLimits, PackageValidationError
from mikazuki.plugin_marketplace.paths import MarketplacePaths, PathPolicyError
from mikazuki.plugin_marketplace.store import MarketplaceStore
from mikazuki.plugin_marketplace.trust import TrustError, TrustStore, canonical_entry_payload
from mikazuki.plugin_host.runtime import RuntimeSnapshot
from mikazuki.plugin_host.runtime import ExecutablePluginRuntime, _ProcessHandle


HOST_VERSION = "2.9.2"


def manifest_dict(*, version: str = "0.1.0", install_hooks: list[str] | None = None) -> dict:
    return {
        "id": "next-trainer-pi-agent",
        "publisher": "approved-publisher-id",
        "version": version,
        "protocolVersion": "1",
        "hostCompatibility": ">=2.9.2 <3.0.0",
        "platforms": ["win32-x64"],
        "runtime": {
            "kind": "executable",
            "entrypoint": "bin/next-trainer-pi-sidecar.exe",
            "buildNode": "22.19.0",
            "embeddedRuntime": "bun-1.4.0",
        },
        "ui": {
            "entrypoint": "ui/index.js",
            "settingsEntrypoint": "ui/settings.js",
            "extensionApi": "1",
            "placements": ["floating-panel", "artifact-detail"],
        },
        "bridge": {"requests": [], "streams": []},
        "capabilities": ["session", "events"],
        "permissions": ["model-provider", "training-config"],
        "package": {"sha256": "catalog-owned", "signature": "catalog-owned", "sbom": "sbom.cdx.json"},
        "installHooks": install_hooks or [],
    }


def build_package(root: Path, *, version: str = "0.1.0", manifest: dict | None = None) -> Path:
    package = root / f"agent-{version}.zip"
    payload = manifest or manifest_dict(version=version)
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(payload))
        archive.writestr("bin/next-trainer-pi-sidecar.exe", b"mock executable")
        archive.writestr("ui/index.js", "export default {}")
        if payload.get("ui", {}).get("settingsEntrypoint"):
            archive.writestr(payload["ui"]["settingsEntrypoint"], "export const settings = true")
        archive.writestr("sbom.cdx.json", '{"bomFormat":"CycloneDX"}')
        archive.writestr("LICENSE", "MIT")
    return package


def signed_entry(package: Path, key: bytes, *, version: str = "0.1.0", **overrides) -> MarketplaceEntry:
    data = {
        "id": "next-trainer-pi-agent",
        "name": "Next Trainer Pi Agent",
        "publisher_id": "approved-publisher-id",
        "description": "Optional agent",
        "latest_version": version,
        "channel": "stable",
        "host_compatibility": ">=2.9.2 <3.0.0",
        "platforms": ["win32-x64"],
        "package_size": package.stat().st_size,
        "permissions_summary": ["model-provider", "training-config"],
        "license": "MIT",
        "package_url": "https://market.invalid/plugins/agent.zip",
        "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "signing_key_id": "test-key",
        "published_at": "2026-08-21T00:00:00Z",
        "signature": "",
    }
    data.update(overrides)
    entry = MarketplaceEntry.model_validate(data)
    data["signature"] = hmac.new(key, canonical_entry_payload(entry), hashlib.sha256).hexdigest()
    return MarketplaceEntry.model_validate(data)


def manager_for(root: Path, *, health=None, runtime=None) -> tuple[MarketplaceManager, bytes]:
    key = b"stage-1-mock-signing-key"
    paths = MarketplacePaths(root)
    return (
        MarketplaceManager(
            paths=paths,
            store=MarketplaceStore(paths.registry_file),
            trust=TrustStore({"test-key": ("approved-publisher-id", key)}),
            host_version=HOST_VERSION,
            platform="win32-x64",
            health_check=health,
            runtime=runtime,
        ),
        key,
    )


def test_manifest_rejects_unknown_fields_and_arbitrary_install_hooks():
    valid = manifest_dict()
    assert PluginManifest.model_validate(valid).id == "next-trainer-pi-agent"

    with pytest.raises(ValidationError):
        PluginManifest.model_validate({**valid, "unexpected": True})

    with pytest.raises(ValidationError):
        PluginManifest.model_validate(manifest_dict(install_hooks=["powershell -File install.ps1"]))


def test_manifest_bridge_requires_declared_permission_and_strict_local_json_schema():
    valid = manifest_dict()
    valid["bridge"]["requests"] = [
        {
            "method": "session.list",
            "permission": "model-provider",
            "paramsSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        }
    ]
    assert PluginManifest.model_validate(valid).bridge.requests[0].method == "session.list"

    undeclared = json.loads(json.dumps(valid))
    undeclared["bridge"]["requests"][0]["permission"] = "dataset-review"
    with pytest.raises(ValidationError, match="not declared"):
        PluginManifest.model_validate(undeclared)

    referenced = json.loads(json.dumps(valid))
    referenced["bridge"]["requests"][0]["paramsSchema"] = {
        "type": "object",
        "$ref": "https://attacker.invalid/schema.json",
        "additionalProperties": False,
    }
    with pytest.raises(ValidationError, match="unsupported keywords"):
        PluginManifest.model_validate(referenced)


@pytest.mark.parametrize("unsafe", ["../agent", "agent/child", "C:agent", "agent\\child", ""])
def test_paths_reject_unsafe_identifiers(unsafe: str):
    with tempfile.TemporaryDirectory() as td:
        paths = MarketplacePaths(Path(td))
        with pytest.raises(PathPolicyError):
            paths.plugin_versions(unsafe)


def test_store_writes_atomically_and_recovers_invalid_json():
    with tempfile.TemporaryDirectory() as td:
        registry = Path(td) / "registry.json"
        store = MarketplaceStore(registry)
        store.set_plugin("next-trainer-pi-agent", {"active_version": "0.1.0", "enabled": False})
        assert json.loads(registry.read_text(encoding="utf-8"))["plugins"]["next-trainer-pi-agent"]["active_version"] == "0.1.0"
        assert not registry.with_suffix(".json.tmp").exists()

        registry.write_text("{broken", encoding="utf-8")
        with pytest.raises(ValueError, match="invalid marketplace registry"):
            MarketplaceStore(registry).snapshot()


def test_trust_rejects_hash_signature_unknown_and_revoked_key():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        package = build_package(root)
        key = b"trusted"
        entry = signed_entry(package, key)
        trust = TrustStore({"test-key": ("approved-publisher-id", key)})
        trust.verify(entry, package)

        package.write_bytes(package.read_bytes() + b"tamper")
        with pytest.raises(TrustError, match="size|sha256"):
            trust.verify(entry, package)

        fresh = build_package(root)
        entry = signed_entry(fresh, key)
        with pytest.raises(TrustError, match="unknown signing key"):
            TrustStore({}).verify(entry, fresh)
        with pytest.raises(TrustError, match="revoked"):
            TrustStore({"test-key": ("approved-publisher-id", key)}, revoked_keys={"test-key"}).verify(entry, fresh)


def test_install_enable_disable_update_rollback_and_uninstall_preserves_user_data():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manager, key = manager_for(root)

        package_v1 = build_package(root, version="0.1.0")
        status = manager.install(signed_entry(package_v1, key, version="0.1.0"), package_v1)
        assert status.active_version == "0.1.0"
        assert status.enabled is False
        assert manager.paths.version_dir(status.id, "0.1.0").is_dir()

        permissions = {"model-provider", "training-config"}
        enabled = manager.enable(status.id, permissions)
        assert enabled.enabled is True
        assert set(enabled.granted_permissions) == permissions
        disabled = manager.disable(status.id)
        assert disabled.enabled is False
        assert set(disabled.granted_permissions) == permissions

        package_v2 = build_package(root, version="0.2.0")
        updated = manager.install(signed_entry(package_v2, key, version="0.2.0"), package_v2)
        assert updated.active_version == "0.2.0"
        assert updated.previous_version == "0.1.0"
        rolled_back = manager.rollback(updated.id)
        assert rolled_back.active_version == "0.1.0"

        data_dir = manager.paths.user_data_dir(updated.id)
        data_dir.mkdir(parents=True)
        (data_dir / "auth.json").write_text("{}", encoding="utf-8")
        removed = manager.uninstall(updated.id)
        assert removed.state == "not_installed"
        assert data_dir.is_dir()
        assert not manager.paths.plugin_root(updated.id).exists()


def test_failed_update_health_keeps_old_active_version_and_cleans_staging():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        def health(manifest: PluginManifest, _directory: Path) -> bool:
            return manifest.version != "0.2.0"

        manager, key = manager_for(root, health=health)
        package_v1 = build_package(root, version="0.1.0")
        manager.install(signed_entry(package_v1, key, version="0.1.0"), package_v1)

        package_v2 = build_package(root, version="0.2.0")
        with pytest.raises(RuntimeError, match="health check failed"):
            manager.install(signed_entry(package_v2, key, version="0.2.0"), package_v2)

        status = manager.status("next-trainer-pi-agent")
        assert status.active_version == "0.1.0"
        assert not manager.paths.version_dir(status.id, "0.2.0").exists()
        assert list(manager.paths.staging_root.glob("*")) == []


def test_verified_update_preserves_explicit_enabled_state():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manager, key = manager_for(root)
        package_v1 = build_package(root, version="0.1.0")
        manager.install(signed_entry(package_v1, key, version="0.1.0"), package_v1)
        manager.enable("next-trainer-pi-agent", {"model-provider", "training-config"})

        package_v2 = build_package(root, version="0.2.0")
        status = manager.install(signed_entry(package_v2, key, version="0.2.0"), package_v2)

        assert status.active_version == "0.2.0"
        assert status.enabled is True
        assert status.state == "enabled"


def test_archive_rejects_path_traversal_and_file_count_limit():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manager, key = manager_for(root)
        malicious = root / "malicious.zip"
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("../escape.txt", "no")
            archive.writestr("plugin.json", json.dumps(manifest_dict()))
        entry = signed_entry(malicious, key)
        with pytest.raises(PackageValidationError, match="unsafe archive path"):
            manager.install(entry, malicious)

        crowded = root / "crowded.zip"
        with zipfile.ZipFile(crowded, "w") as archive:
            archive.writestr("plugin.json", json.dumps(manifest_dict()))
            archive.writestr("one", "1")
            archive.writestr("two", "2")
        entry = signed_entry(crowded, key)
        manager.package_limits = PackageLimits(max_files=2)
        with pytest.raises(PackageValidationError, match="file count"):
            manager.install(entry, crowded)


def test_manifest_entry_identity_compatibility_platform_and_permissions_must_match():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manager, key = manager_for(root)

        package = build_package(root, manifest=manifest_dict(version="9.9.9"))
        with pytest.raises(PackageValidationError, match="version does not match"):
            manager.install(signed_entry(package, key, version="0.1.0"), package)

        package = build_package(root)
        entry = signed_entry(package, key, host_compatibility=">=3.0.0", platforms=["linux-x64"])
        with pytest.raises(TrustError, match="host compatibility"):
            manager.install(entry, package)

        with pytest.raises(ValidationError, match="unregistered plugin permissions"):
            signed_entry(package, key, permissions_summary=["shell"])

        shell_manifest = manifest_dict()
        shell_manifest["permissions"] = ["shell"]
        with pytest.raises(ValidationError, match="permission"):
            PluginManifest.model_validate(shell_manifest)


def test_catalog_package_url_rejects_credentials_fragments_and_non_public_ip():
    with tempfile.TemporaryDirectory() as td:
        package = build_package(Path(td))
        key = b"trusted"
        for url in (
            "http://market.invalid/agent.zip",
            "https://user:password@market.invalid/agent.zip",
            "https://market.invalid/agent.zip#fragment",
            "https://127.0.0.1/agent.zip",
            "https://192.168.1.4/agent.zip",
        ):
            with pytest.raises(ValidationError, match="package_url"):
                signed_entry(package, key, package_url=url)


def test_runtime_child_environment_does_not_inherit_host_secrets(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-private")
    monkeypatch.setenv("HTTP_PROXY", "http://attacker.invalid")
    monkeypatch.setenv("TEMP", r"C:\Temp")
    environment = ExecutablePluginRuntime._child_environment()
    assert "DEEPSEEK_API_KEY" not in environment
    assert "HTTP_PROXY" not in environment
    assert environment["TEMP"] == r"C:\Temp"
    assert environment["SystemRoot"].casefold() == environment["WINDIR"].casefold()
    assert environment["PATH"].casefold() == f"{environment['SystemRoot']}\\System32;{environment['SystemRoot']}".casefold()


def test_executable_runtime_forwards_authenticated_request_and_stream_wire_contract():
    received: list[tuple[str, dict]] = []
    request_id = "d8994c20-f3b6-4c72-b52a-1aad041e849e"

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/health" or self.headers.get("Authorization") != "Bearer sidecar-secret":
                self.send_error(403)
                return
            body = json.dumps(
                {
                    "ok": True,
                    "requestId": self.headers.get("X-Request-Id"),
                    "data": {"status": "ok", "protocolVersion": "1"},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            assert self.headers.get("Authorization") == "Bearer sidecar-secret"
            assert self.headers.get("X-Request-Id") == request_id
            received.append((self.path, payload))
            envelope = {"ok": True, "requestId": request_id, "data": {"wire": self.path}}
            if self.path == "/bridge/requests":
                body = json.dumps(envelope).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/bridge/streams":
                # No final blank frame: EOF must still dispatch the buffered SSE event.
                body = ("event: data\ndata: " + json.dumps(envelope)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def log_message(self, _format, *_args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class Process:
        pid = 999

        @staticmethod
        def poll():
            return None

    runtime = ExecutablePluginRuntime()
    runtime._handles["next-trainer-pi-agent"] = _ProcessHandle(
        process=Process(),
        version="0.1.0",
        protocol_version="1",
        port=server.server_port,
        token="sidecar-secret",
        host_tool_token="host-tool-secret",
    )
    try:
        snapshot = runtime.status("next-trainer-pi-agent")
        assert snapshot.state == "running"
        assert runtime.verify_host_tool_token("next-trainer-pi-agent", "host-tool-secret") is True
        assert runtime.verify_host_tool_token("next-trainer-pi-agent", "wrong") is False

        response = asyncio.run(
            runtime.request("next-trainer-pi-agent", request_id, "session.list", {})
        )
        assert response == {"wire": "/bridge/requests"}

        async def collect_stream():
            stream = await runtime.stream(
                "next-trainer-pi-agent",
                request_id,
                "session.subscribe",
                {"sessionId": "session-1"},
            )
            return [event async for event in stream]

        assert asyncio.run(collect_stream()) == [{"wire": "/bridge/streams"}]
        assert received == [
            (
                "/bridge/requests",
                {"requestId": request_id, "method": "session.list", "params": {}},
            ),
            (
                "/bridge/streams",
                {
                    "requestId": request_id,
                    "method": "session.subscribe",
                    "params": {"sessionId": "session-1"},
                },
            ),
        ]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_settings_entrypoint_is_explicit_present_and_confined_to_ui_root():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manager, key = manager_for(root)
        missing = manifest_dict()
        package = root / "missing-settings.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("plugin.json", json.dumps(missing))
            archive.writestr("bin/next-trainer-pi-sidecar.exe", b"mock")
            archive.writestr("ui/index.js", "export default {}")
            archive.writestr("sbom.cdx.json", '{"bomFormat":"CycloneDX"}')
            archive.writestr("LICENSE", "MIT")
        with pytest.raises(PackageValidationError, match="settings UI entrypoint"):
            manager.install(signed_entry(package, key), package)

        escaped = manifest_dict()
        escaped["ui"]["settingsEntrypoint"] = "settings/index.js"
        package = build_package(root, manifest=escaped)
        with pytest.raises(PackageValidationError, match="share the plugin UI root"):
            manager.install(signed_entry(package, key), package)


def test_enabled_update_cannot_inherit_new_permissions_without_approval():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manager, key = manager_for(root)
        package_v1 = build_package(root, version="0.1.0")
        manager.install(signed_entry(package_v1, key, version="0.1.0"), package_v1)
        manager.enable("next-trainer-pi-agent", {"model-provider", "training-config"})

        manifest_v2 = manifest_dict(version="0.2.0")
        manifest_v2["permissions"].append("dataset-review")
        package_v2 = build_package(root, version="0.2.0", manifest=manifest_v2)
        entry_v2 = signed_entry(
            package_v2,
            key,
            version="0.2.0",
            permissions_summary=["model-provider", "training-config", "dataset-review"],
        )
        with pytest.raises(PermissionError, match="requires approval"):
            manager.install(entry_v2, package_v2)
        assert manager.status(entry_v2.id).active_version == "0.1.0"

        updated = manager.install(
            entry_v2,
            package_v2,
            approved_permissions={"model-provider", "training-config", "dataset-review"},
        )
        assert updated.active_version == "0.2.0"
        assert updated.enabled is True


class FakeRuntime:
    def __init__(self) -> None:
        self.running: tuple[str, str] | None = None
        self.starts: list[str] = []
        self.stops: list[str] = []
        self.fail_versions: set[str] = set()
        self.crashed = False

    def start(self, manifest, _package_root: Path, _data_root: Path) -> RuntimeSnapshot:
        self.starts.append(manifest.version)
        if manifest.version in self.fail_versions:
            raise RuntimeError("private executable failure C:/secret/runtime")
        self.running = (manifest.id, manifest.version)
        self.crashed = False
        return RuntimeSnapshot(state="running", version=manifest.version, pid=321, protocol_version="1")

    def stop(self, plugin_id: str) -> None:
        self.stops.append(plugin_id)
        self.running = None

    def status(self, plugin_id: str) -> RuntimeSnapshot:
        if self.running is None or self.running[0] != plugin_id:
            return RuntimeSnapshot(state="stopped")
        if self.crashed:
            return RuntimeSnapshot(state="crashed", version=self.running[1], pid=321, reason="process exited")
        return RuntimeSnapshot(state="running", version=self.running[1], pid=321, protocol_version="1")


def test_runtime_lifecycle_reports_crash_restarts_and_recovers_failed_update():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        runtime = FakeRuntime()
        manager, key = manager_for(root, runtime=runtime)
        permissions = {"model-provider", "training-config"}
        package_v1 = build_package(root, version="0.1.0")
        manager.install(signed_entry(package_v1, key, version="0.1.0"), package_v1)
        enabled = manager.enable("next-trainer-pi-agent", permissions)
        assert enabled.runtime_state == "running"
        assert enabled.runtime_pid == 321

        runtime.crashed = True
        crashed = manager.status("next-trainer-pi-agent")
        assert crashed.state == "runtime_error"
        assert crashed.enabled is True
        restarted = manager.restart("next-trainer-pi-agent")
        assert restarted.state == "enabled"

        runtime.fail_versions.add("0.2.0")
        package_v2 = build_package(root, version="0.2.0")
        with pytest.raises(RuntimeError, match="runtime activation failed"):
            manager.install(signed_entry(package_v2, key, version="0.2.0"), package_v2)
        recovered = manager.status("next-trainer-pi-agent")
        assert recovered.active_version == "0.1.0"
        assert recovered.state == "enabled"
        assert runtime.starts[-2:] == ["0.2.0", "0.1.0"]

        data_dir = manager.paths.user_data_dir(recovered.id)
        data_dir.mkdir(parents=True, exist_ok=True)
        auth = data_dir / "auth.json"
        auth.write_text("{}", encoding="utf-8")
        manager.uninstall(recovered.id)
        assert auth.is_file()
        assert runtime.running is None

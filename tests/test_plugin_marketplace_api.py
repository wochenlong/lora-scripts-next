from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import zipfile
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikazuki.plugin_host import AgentRouteAuthorityConfig, PluginCapabilityBroker, RuntimeSnapshot
from mikazuki.plugin_marketplace.api import (
    _default_authority_config,
    configure_capability_broker,
    configure_confirmation_store,
    configure_marketplace,
    configure_marketplace_catalog,
    configure_marketplace_authority,
    host_router,
    router,
)
from mikazuki.plugin_marketplace.manager import MarketplaceManager
from mikazuki.plugin_marketplace.models import MarketplaceCatalog, MarketplaceEntry
from mikazuki.plugin_marketplace.catalog import FileCatalogSource, LocalPackageAcquirer, MarketplaceCatalogService
from mikazuki.plugin_marketplace.paths import MarketplacePaths
from mikazuki.plugin_marketplace.store import MarketplaceStore
from mikazuki.plugin_marketplace.trust import (
    TrustStore,
    canonical_catalog_payload,
    canonical_entry_payload,
)
from mikazuki.plugin_host import ConfirmationTicketStore


RUN_TOKEN = "marketplace-test-run-token-long-enough"
APP_HOST = "127.0.0.1:28000"
APP_ORIGIN = f"http://{APP_HOST}"
AUTH_HEADERS = {
    "Origin": APP_ORIGIN,
    "Sec-Fetch-Site": "same-origin",
    "X-NextTrainer-Run-Token": RUN_TOKEN,
}


class LoopbackClientScope:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            scope = dict(scope)
            scope["client"] = ("127.0.0.1", 51000)
        await self.app(scope, receive, send)


def _client(*routers) -> TestClient:
    configure_marketplace_authority(
        AgentRouteAuthorityConfig(
            allowed_hosts={APP_HOST},
            allowed_origins={APP_ORIGIN},
            run_token=RUN_TOKEN,
        )
    )
    app = FastAPI()
    for item in routers:
        app.include_router(item, prefix="/api")
    return TestClient(LoopbackClientScope(app), base_url=APP_ORIGIN)


def _package(
    root: Path,
    *,
    version: str = "0.1.0",
    runtime_bridge: bool = False,
    confirmation_bridge: bool = False,
    host_bridge: bool = False,
) -> Path:
    path = root / f"agent-{version}.zip"
    manifest = {
        "id": "next-trainer-pi-agent",
        "publisher": "approved-publisher-id",
        "version": version,
        "protocolVersion": "1",
        "hostCompatibility": ">=2.9.2 <3.0.0",
        "platforms": ["win32-x64"],
        "runtime": {"kind": "executable", "entrypoint": "bin/sidecar.exe"},
        "ui": {
            "entrypoint": "ui/index.js",
            "settingsEntrypoint": "ui/settings.js",
            "extensionApi": "1",
            "placements": ["floating-panel"],
        },
        "bridge": {
            "requests": (
                ([
                    {
                        "method": "session.list",
                        "permission": "model-provider",
                        "paramsSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                    }
                ] if runtime_bridge else [])
                + ([
                    {
                        "method": "confirmation.request",
                        "permission": "model-provider",
                        "paramsSchema": {
                            "type": "object",
                            "properties": {"toolCallId": {"type": "string", "minLength": 1}},
                            "required": ["toolCallId"],
                            "additionalProperties": False,
                        },
                    },
                    {
                        "method": "confirmation.getResult",
                        "permission": "model-provider",
                        "paramsSchema": {
                            "type": "object",
                            "properties": {"ticketId": {"type": "string", "minLength": 1}},
                            "required": ["ticketId"],
                            "additionalProperties": False,
                        },
                    },
                ] if confirmation_bridge else [])
                + ([
                    {
                        "method": "host.context",
                        "permission": "model-provider",
                        "paramsSchema": {"type": "object", "properties": {}, "additionalProperties": True},
                    },
                    {
                        "method": "host.fail",
                        "permission": "model-provider",
                        "paramsSchema": {"type": "object", "properties": {}, "additionalProperties": True},
                    },
                ] if host_bridge else [])
            ),
            "streams": (
                ([
                    {
                        "method": "session.subscribe",
                        "permission": "model-provider",
                        "paramsSchema": {
                            "type": "object",
                            "properties": {"sessionId": {"type": "string", "minLength": 1}},
                            "required": ["sessionId"],
                            "additionalProperties": False,
                        },
                    }
                ] if runtime_bridge else [])
                + ([
                    {
                        "method": "host.subscribe",
                        "permission": "model-provider",
                        "paramsSchema": {"type": "object", "properties": {}, "additionalProperties": True},
                    }
                ] if host_bridge else [])
            ),
        },
        "capabilities": ["session"],
        "permissions": ["model-provider"],
        "package": {"sha256": "catalog-owned", "signature": "catalog-owned", "sbom": "sbom.cdx.json"},
        "installHooks": [],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("plugin.json", json.dumps(manifest))
        archive.writestr("bin/sidecar.exe", "binary")
        archive.writestr("ui/index.js", "export const plugin = true")
        archive.writestr("ui/settings.js", "export const settings = true")
        archive.writestr("sbom.cdx.json", '{"bomFormat":"CycloneDX"}')
        archive.writestr("LICENSE", "MIT")
    return path


def _entry(package: Path, key: bytes, *, version: str = "0.1.0") -> MarketplaceEntry:
    value = {
        "id": "next-trainer-pi-agent",
        "name": "Agent",
        "publisher_id": "approved-publisher-id",
        "latest_version": version,
        "channel": "stable",
        "host_compatibility": ">=2.9.2 <3.0.0",
        "platforms": ["win32-x64"],
        "package_size": package.stat().st_size,
        "permissions_summary": ["model-provider"],
        "license": "MIT",
        "package_url": "https://market.invalid/agent.zip",
        "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "signature": "",
        "signing_key_id": "mock-key",
        "published_at": "2026-08-21T00:00:00Z",
    }
    unsigned = MarketplaceEntry.model_validate(value)
    value["signature"] = hmac.new(key, canonical_entry_payload(unsigned), hashlib.sha256).hexdigest()
    return MarketplaceEntry.model_validate(value)


def _configure_catalog(
    root: Path,
    paths: MarketplacePaths,
    trust: TrustStore,
    entry: MarketplaceEntry,
    key: bytes,
    package: Path,
) -> MarketplaceCatalogService:
    value = {
        "schemaVersion": 1,
        "publisherId": "approved-publisher-id",
        "signingKeyId": "mock-key",
        "generatedAt": "2026-08-21T00:00:00Z",
        "entries": [entry.model_dump(mode="json")],
        "signature": "",
    }
    unsigned = MarketplaceCatalog.model_validate(value)
    value["signature"] = hmac.new(key, canonical_catalog_payload(unsigned), hashlib.sha256).hexdigest()
    catalog = MarketplaceCatalog.model_validate(value)
    source = root / "catalog.json"
    source.write_text(json.dumps(catalog.model_dump(mode="json", by_alias=True)), encoding="utf-8")
    service = MarketplaceCatalogService(
        paths=paths,
        trust=trust,
        source=FileCatalogSource(source),
        acquirer=LocalPackageAcquirer({entry.package_url: package}),
    )
    service.refresh()
    configure_marketplace_catalog(service)
    return service


def test_marketplace_and_plugin_host_routes_use_separate_namespaces():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        paths = MarketplacePaths(root / "marketplace")
        key = b"mock-key"
        trust = TrustStore({"mock-key": ("approved-publisher-id", key)})
        manager = MarketplaceManager(
            paths=paths,
            store=MarketplaceStore(paths.registry_file),
            trust=trust,
            host_version="2.9.2",
            platform="win32-x64",
        )
        configure_marketplace(manager)
        configure_capability_broker(PluginCapabilityBroker())
        package = _package(root)
        entry = _entry(package, key)
        _configure_catalog(root, paths, trust, entry, key, package)

        client = _client(router, host_router)

        bootstrap = client.post(
            "/api/plugin-host/bootstrap",
            json={},
            headers={"Origin": APP_ORIGIN, "Sec-Fetch-Site": "same-origin"},
        )
        assert bootstrap.status_code == 200
        assert bootstrap.json()["data"]["runToken"] == RUN_TOKEN
        assert bootstrap.headers["cache-control"] == "no-store"

        response = client.get(f"/api/marketplace/plugins/{entry.id}")
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "not_installed"

        catalog = client.get("/api/marketplace/catalog")
        assert catalog.status_code == 200
        assert catalog.json()["data"][0]["publisher_id"] == "approved-publisher-id"
        detail = client.get(f"/api/marketplace/catalog/{entry.id}")
        assert detail.json()["data"]["permissions_summary"] == ["model-provider"]

        response = client.post(
            f"/api/marketplace/plugins/{entry.id}/install",
            json={},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["active_version"] == "0.1.0"

        assert client.get("/api/plugin-host/extensions").json()["data"]["extensions"] == []
        response = client.post(
            f"/api/marketplace/plugins/{entry.id}/enable",
            json={"permissions": ["model-provider"]},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        extensions = client.get("/api/plugin-host/extensions").json()["data"]["extensions"]
        assert extensions[0]["pluginId"] == entry.id
        assert extensions[0]["displayName"] == "Agent"
        assert extensions[0]["capabilities"] == []
        assert extensions[0]["ui"]["floatingPanel"]["entryUrl"].startswith("/api/plugin-host/ui/")
        assert extensions[0]["ui"]["settings"]["entryUrl"].endswith("/settings.js")

        artifact = client.get(f"/api/plugin-host/ui/{entry.id}/0.1.0/index.js")
        assert artifact.status_code == 200
        assert "plugin = true" in artifact.text
        assert "connect-src 'none'" in artifact.headers["content-security-policy"]
        assert "default-src 'none'" in artifact.headers["content-security-policy"]
        assert artifact.headers["x-content-type-options"] == "nosniff"
        assert artifact.headers["cache-control"] == "public, max-age=31536000, immutable"

        missing_artifact = client.get(f"/api/plugin-host/ui/{entry.id}/0.1.0/missing.js")
        assert missing_artifact.status_code == 404
        assert missing_artifact.json()["detail"] == {
            "code": "MARKETPLACE_NOT_FOUND",
            "message": "Requested marketplace resource was not found.",
        }
        assert str(root) not in missing_artifact.text

        client.post(f"/api/marketplace/plugins/{entry.id}/disable", json={}, headers=AUTH_HEADERS)
        assert client.get("/api/plugin-host/extensions").json()["data"]["extensions"] == []
        forbidden_artifact = client.get(f"/api/plugin-host/ui/{entry.id}/0.1.0/index.js")
        assert forbidden_artifact.status_code == 403
        assert forbidden_artifact.json()["detail"] == {
            "code": "MARKETPLACE_FORBIDDEN",
            "message": "Marketplace operation is not permitted.",
        }
        assert str(root) not in forbidden_artifact.text
        data_dir = paths.user_data_dir(entry.id)
        data_dir.mkdir(parents=True)
        auth_file = data_dir / "auth.json"
        auth_file.write_text("{}", encoding="utf-8")
        dangerous = client.post(
            f"/api/marketplace/plugins/{entry.id}/uninstall",
            json={"delete_user_data": True},
            headers=AUTH_HEADERS,
        )
        assert dangerous.status_code == 422
        assert auth_file.is_file()
        response = client.post(
            f"/api/marketplace/plugins/{entry.id}/uninstall",
            json={},
            headers=AUTH_HEADERS,
        )
        assert response.json()["data"]["state"] == "not_installed"
        assert auth_file.is_file()


def test_install_route_rejects_catalog_id_mismatch():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        paths = MarketplacePaths(root / "marketplace")
        key = b"mock-key"
        trust = TrustStore({"mock-key": ("approved-publisher-id", key)})
        configure_marketplace(
            MarketplaceManager(
                paths=paths,
                store=MarketplaceStore(paths.registry_file),
                trust=trust,
                host_version="2.9.2",
                platform="win32-x64",
            )
        )
        package = _package(root)
        entry = _entry(package, key)
        _configure_catalog(root, paths, trust, entry, key, package)
        client = _client(router)
        response = client.post(
            "/api/marketplace/plugins/some-other-plugin/install",
            json={},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "MARKETPLACE_ENTRY_NOT_FOUND"

        package.unlink()
        missing_package = client.post(
            f"/api/marketplace/plugins/{entry.id}/install",
            json={},
            headers=AUTH_HEADERS,
        )
        assert missing_package.status_code == 503
        assert missing_package.json()["detail"] == {
            "code": "MARKETPLACE_PACKAGE_UNAVAILABLE",
            "message": "The marketplace package is unavailable.",
        }
        assert str(root) not in missing_package.text


def test_marketplace_mutations_require_exact_loopback_authority():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        paths = MarketplacePaths(root / "marketplace")
        key = b"mock-key"
        trust = TrustStore({"mock-key": ("approved-publisher-id", key)})
        configure_marketplace(
            MarketplaceManager(
                paths=paths,
                store=MarketplaceStore(paths.registry_file),
                trust=trust,
                host_version="2.9.2",
                platform="win32-x64",
            )
        )
        package = _package(root)
        entry = _entry(package, key)
        _configure_catalog(root, paths, trust, entry, key, package)
        client = _client(router)
        path = f"/api/marketplace/plugins/{entry.id}/install"
        body = {}

        missing = client.post(path, json=body, headers={"Origin": APP_ORIGIN})
        assert missing.status_code == 403
        assert missing.json()["detail"]["reason"] == "run-token"
        cross_site = client.post(
            path,
            json=body,
            headers={**AUTH_HEADERS, "Origin": "http://attacker.invalid", "Sec-Fetch-Site": "cross-site"},
        )
        assert cross_site.status_code == 403
        assert cross_site.json()["detail"]["reason"] == "cross-site"
        assert paths.version_dir(entry.id, entry.latest_version).exists() is False


def test_default_authority_disables_remote_listen_and_supports_bracketed_ipv6(monkeypatch):
    monkeypatch.setenv("MIKAZUKI_HOST", "0.0.0.0")
    monkeypatch.setenv("MIKAZUKI_PORT", "28000")
    assert _default_authority_config() is None

    monkeypatch.setenv("MIKAZUKI_HOST", "::1")
    config = _default_authority_config()
    assert config is not None
    assert config.allowed_hosts == frozenset({"[::1]:28000"})
    assert config.allowed_origins == frozenset({"http://[::1]:28000"})

    configure_marketplace_authority(None)
    app = FastAPI()
    app.include_router(host_router, prefix="/api")
    remote_client = TestClient(app)
    assert remote_client.get("/api/plugin-host/extensions").json()["data"]["extensions"] == []
    artifact = remote_client.get("/api/plugin-host/ui/next-trainer-pi-agent/0.1.0/index.js")
    assert artifact.status_code == 403
    assert artifact.json()["detail"]["reason"] == "disabled"


def test_generic_broker_checks_grants_and_sanitizes_request_and_stream_failures():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        paths = MarketplacePaths(root / "marketplace")
        key = b"mock-key"
        manager = MarketplaceManager(
            paths=paths,
            store=MarketplaceStore(paths.registry_file),
            trust=TrustStore({"mock-key": ("approved-publisher-id", key)}),
            host_version="2.9.2",
            platform="win32-x64",
        )
        configure_marketplace(manager)
        package = _package(root, host_bridge=True)
        entry = _entry(package, key)
        manager.install(entry, package)
        manager.enable(entry.id, {"model-provider"})

        broker = PluginCapabilityBroker()
        broker.register_request(
            "host.context",
            {"model-provider"},
            lambda context, params: {"pluginId": context.plugin_id, "params": params},
        )
        broker.register_request(
            "dataset.commit",
            {"dataset-review"},
            lambda _context, _params: {"mustNotRun": True},
        )

        def fail_request(_context, _params):
            raise RuntimeError("C:/private/auth.json sk-private")

        broker.register_request("host.fail", {"model-provider"}, fail_request)

        async def finite_stream(_context, _params) -> AsyncIterator[dict]:
            yield {"type": "snapshot", "runId": 1}
            raise RuntimeError("C:/private/session.jsonl")

        broker.register_stream("host.subscribe", {"model-provider"}, finite_stream)
        configure_capability_broker(broker)
        client = _client(host_router)
        request_id = "b479967c-8406-4b1f-84e0-f0ebf24de38e"

        extensions = client.get("/api/plugin-host/extensions").json()["data"]["extensions"]
        assert extensions[0]["capabilities"] == [
            "host.context",
            "host.fail",
            "host.subscribe",
        ]

        response = client.post(
            f"/api/plugin-host/extensions/{entry.id}/requests",
            json={"requestId": request_id, "method": "host.context", "params": {"cursor": "1"}},
            headers=AUTH_HEADERS,
        )
        assert response.json() == {
            "ok": True,
            "requestId": request_id,
            "data": {"pluginId": entry.id, "params": {"cursor": "1"}},
        }

        denied = client.post(
            f"/api/plugin-host/extensions/{entry.id}/requests",
            json={"requestId": request_id, "method": "dataset.commit", "params": {}},
            headers=AUTH_HEADERS,
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "PLUGIN_CAPABILITY_FORBIDDEN"

        failed = client.post(
            f"/api/plugin-host/extensions/{entry.id}/requests",
            json={"requestId": request_id, "method": "host.fail", "params": {}},
            headers=AUTH_HEADERS,
        )
        assert failed.status_code == 500
        assert failed.json()["error"] == {
            "code": "PLUGIN_CAPABILITY_FAILED",
            "message": "The plugin capability request failed.",
            "retryable": False,
        }
        assert "private" not in failed.text

        streamed = client.post(
            f"/api/plugin-host/extensions/{entry.id}/streams",
            json={"requestId": request_id, "method": "host.subscribe", "params": {}},
            headers=AUTH_HEADERS,
        )
        assert streamed.status_code == 200
        assert '"type": "snapshot"' in streamed.text
        assert "PLUGIN_STREAM_FAILED" in streamed.text
        assert "private" not in streamed.text


class FakeForwardingRuntime:
    def __init__(self) -> None:
        self.running = False
        self.requests: list[tuple[str, str, dict]] = []

    def start(self, manifest, _package_root: Path, _data_root: Path) -> RuntimeSnapshot:
        self.running = True
        return RuntimeSnapshot(state="running", version=manifest.version, pid=456, protocol_version="1")

    def stop(self, _plugin_id: str) -> None:
        self.running = False

    def status(self, _plugin_id: str) -> RuntimeSnapshot:
        return RuntimeSnapshot(state="running", version="0.1.0", pid=456, protocol_version="1")

    async def request(self, _plugin_id: str, request_id: str, method: str, params: dict):
        self.requests.append((request_id, method, params))
        return {"sessions": []}

    async def stream(self, _plugin_id: str, request_id: str, method: str, params: dict):
        self.requests.append((request_id, method, params))

        async def events():
            yield {"type": "snapshot", "sessionId": params["sessionId"]}

        return events()


def test_manifest_declared_bridge_forwards_through_runtime_without_core_agent_handlers():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        paths = MarketplacePaths(root / "marketplace")
        key = b"mock-key"
        runtime = FakeForwardingRuntime()
        manager = MarketplaceManager(
            paths=paths,
            store=MarketplaceStore(paths.registry_file),
            trust=TrustStore({"mock-key": ("approved-publisher-id", key)}),
            host_version="2.9.2",
            platform="win32-x64",
            runtime=runtime,
        )
        configure_marketplace(manager)
        configure_capability_broker(PluginCapabilityBroker())
        package = _package(root, runtime_bridge=True)
        entry = _entry(package, key)
        manager.install(entry, package)
        manager.enable(entry.id, {"model-provider"})
        client = _client(host_router)
        request_id = "7545369f-7fc2-419d-bc62-14a642f7fe3c"

        extensions = client.get("/api/plugin-host/extensions").json()["data"]["extensions"]
        assert extensions[0]["capabilities"] == ["session.list", "session.subscribe"]
        response = client.post(
            f"/api/plugin-host/extensions/{entry.id}/requests",
            json={"requestId": request_id, "method": "session.list", "params": {}},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["data"] == {"sessions": []}
        assert runtime.requests[-1] == (request_id, "session.list", {})

        invalid = client.post(
            f"/api/plugin-host/extensions/{entry.id}/requests",
            json={"requestId": request_id, "method": "session.list", "params": {"unexpected": True}},
            headers=AUTH_HEADERS,
        )
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "PLUGIN_CAPABILITY_PARAMS_INVALID"
        assert runtime.requests[-1] == (request_id, "session.list", {})

        stream = client.post(
            f"/api/plugin-host/extensions/{entry.id}/streams",
            json={
                "requestId": request_id,
                "method": "session.subscribe",
                "params": {"sessionId": "session-1"},
            },
            headers=AUTH_HEADERS,
        )
        assert stream.status_code == 200
        assert '"sessionId": "session-1"' in stream.text
        assert runtime.requests[-1] == (request_id, "session.subscribe", {"sessionId": "session-1"})


def test_host_confirmation_is_one_shot_expires_and_cannot_be_resolved_by_plugin():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        paths = MarketplacePaths(root / "marketplace")
        key = b"mock-key"
        manager = MarketplaceManager(
            paths=paths,
            store=MarketplaceStore(paths.registry_file),
            trust=TrustStore({"mock-key": ("approved-publisher-id", key)}),
            host_version="2.9.2",
            platform="win32-x64",
        )
        configure_marketplace(manager)
        broker = PluginCapabilityBroker()
        configure_capability_broker(broker)
        now = [datetime(2026, 8, 21, tzinfo=timezone.utc)]
        confirmations = ConfirmationTicketStore(clock=lambda: now[0])
        configure_confirmation_store(confirmations)
        package = _package(root, confirmation_bridge=True)
        entry = _entry(package, key)
        manager.install(entry, package)
        manager.enable(entry.id, {"model-provider"})
        ticket = confirmations.create_pending(
            plugin_id=entry.id,
            tool_call_id="tool-call-1",
            permission="model-provider",
            action="provider.removeKey",
            title="Remove Provider key",
            summary="Remove the configured credential.",
            artifact_ids=["provider-profile"],
            ttl_seconds=60,
        )
        client = _client(host_router)
        request_id = "00c7f636-c7dc-45e4-9071-d12220ec37df"

        projected = client.post(
            f"/api/plugin-host/extensions/{entry.id}/requests",
            json={"requestId": request_id, "method": "confirmation.request", "params": {"toolCallId": "tool-call-1"}},
            headers=AUTH_HEADERS,
        )
        assert projected.status_code == 200
        assert projected.json()["data"] == {
            "ticketId": ticket.ticket_id,
            "pluginId": entry.id,
            "toolCallId": "tool-call-1",
            "permission": "model-provider",
            "title": "Remove Provider key",
            "summary": "Remove the configured credential.",
            "details": {},
            "state": "presented",
            "action": "provider.removeKey",
            "createdAt": now[0].isoformat(),
            "expiresAt": (now[0] + timedelta(seconds=60)).isoformat(),
            "resolvedAt": None,
            "artifactIds": ["provider-profile"],
        }
        pending = client.get("/api/plugin-host/confirmations/pending", headers=AUTH_HEADERS)
        assert pending.json()["data"]["confirmations"][0]["ticketId"] == ticket.ticket_id

        plugin_resolve = client.post(
            f"/api/plugin-host/extensions/{entry.id}/requests",
            json={"requestId": request_id, "method": "confirmation.resolve", "params": {"ticketId": ticket.ticket_id}},
            headers=AUTH_HEADERS,
        )
        assert plugin_resolve.status_code == 404
        assert plugin_resolve.json()["error"]["code"] == "PLUGIN_CAPABILITY_UNAVAILABLE"

        missing_authority = client.post(
            f"/api/plugin-host/confirmations/{ticket.ticket_id}/resolve",
            json={"decision": "approved"},
            headers={"Origin": APP_ORIGIN},
        )
        assert missing_authority.status_code == 403
        resolved = client.post(
            f"/api/plugin-host/confirmations/{ticket.ticket_id}/resolve",
            json={"decision": "approved"},
            headers=AUTH_HEADERS,
        )
        assert resolved.status_code == 200
        assert resolved.json()["data"]["state"] == "approved"
        replay = client.post(
            f"/api/plugin-host/confirmations/{ticket.ticket_id}/resolve",
            json={"decision": "rejected"},
            headers=AUTH_HEADERS,
        )
        assert replay.status_code == 409
        assert replay.json()["detail"]["code"] == "CONFIRMATION_REPLAY_REJECTED"

        result = client.post(
            f"/api/plugin-host/extensions/{entry.id}/requests",
            json={"requestId": request_id, "method": "confirmation.getResult", "params": {"ticketId": ticket.ticket_id}},
            headers=AUTH_HEADERS,
        )
        assert result.status_code == 200
        assert result.json()["data"]["state"] == "approved"

        expiring = confirmations.create_pending(
            plugin_id=entry.id,
            tool_call_id="tool-call-2",
            permission="model-provider",
            action="provider.removeKey",
            title="Expired action",
            summary="",
            ttl_seconds=1,
        )
        now[0] += timedelta(seconds=2)
        expired = client.post(
            f"/api/plugin-host/confirmations/{expiring.ticket_id}/resolve",
            json={"decision": "approved"},
            headers=AUTH_HEADERS,
        )
        assert expired.status_code == 410
        assert expired.json()["detail"]["code"] == "CONFIRMATION_EXPIRED"

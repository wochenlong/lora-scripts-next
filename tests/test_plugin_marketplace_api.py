from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikazuki.plugin_marketplace.api import configure_marketplace, host_router, router
from mikazuki.plugin_marketplace.manager import MarketplaceManager
from mikazuki.plugin_marketplace.models import MarketplaceEntry
from mikazuki.plugin_marketplace.paths import MarketplacePaths
from mikazuki.plugin_marketplace.store import MarketplaceStore
from mikazuki.plugin_marketplace.trust import TrustStore, canonical_entry_payload


def _package(root: Path) -> Path:
    path = root / "agent.zip"
    manifest = {
        "id": "next-trainer-pi-agent",
        "publisher": "approved-publisher-id",
        "version": "0.1.0",
        "protocolVersion": "1",
        "hostCompatibility": ">=2.9.2 <3.0.0",
        "platforms": ["win32-x64"],
        "runtime": {"kind": "executable", "entrypoint": "bin/sidecar.exe"},
        "ui": {"entrypoint": "ui/index.js", "extensionApi": "1", "placements": ["floating-panel"]},
        "capabilities": ["session"],
        "permissions": ["model-provider"],
        "package": {"sha256": "catalog-owned", "signature": "catalog-owned", "sbom": "sbom.cdx.json"},
        "installHooks": [],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("plugin.json", json.dumps(manifest))
        archive.writestr("bin/sidecar.exe", "binary")
        archive.writestr("ui/index.js", "export const plugin = true")
        archive.writestr("sbom.cdx.json", "{}")
        archive.writestr("LICENSE", "MIT")
    return path


def _entry(package: Path, key: bytes) -> MarketplaceEntry:
    value = {
        "id": "next-trainer-pi-agent",
        "name": "Agent",
        "publisher_id": "approved-publisher-id",
        "latest_version": "0.1.0",
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


def test_marketplace_and_plugin_host_routes_use_separate_namespaces():
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
        package = _package(root)
        entry = _entry(package, key)
        quarantine = paths.quarantine_package(entry.id, entry.latest_version)
        quarantine.parent.mkdir(parents=True)
        shutil.copy2(package, quarantine)

        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.include_router(host_router, prefix="/api")
        client = TestClient(app)

        response = client.get(f"/api/marketplace/plugins/{entry.id}")
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "not_installed"

        response = client.post(
            f"/api/marketplace/plugins/{entry.id}/install",
            json={"entry": entry.model_dump(mode="json")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["active_version"] == "0.1.0"

        assert client.get("/api/plugin-host/extensions").json()["data"]["extensions"] == []
        response = client.post(f"/api/marketplace/plugins/{entry.id}/enable")
        assert response.status_code == 200
        extensions = client.get("/api/plugin-host/extensions").json()["data"]["extensions"]
        assert extensions[0]["pluginId"] == entry.id
        assert extensions[0]["displayName"] == "Agent"
        assert extensions[0]["ui"]["floatingPanel"]["entryUrl"].startswith("/api/plugin-host/ui/")

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

        client.post(f"/api/marketplace/plugins/{entry.id}/disable")
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
        )
        assert dangerous.status_code == 422
        assert auth_file.is_file()
        response = client.post(f"/api/marketplace/plugins/{entry.id}/uninstall", json={})
        assert response.json()["data"]["state"] == "not_installed"
        assert auth_file.is_file()


def test_install_route_rejects_catalog_id_mismatch():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        paths = MarketplacePaths(root / "marketplace")
        key = b"mock-key"
        configure_marketplace(
            MarketplaceManager(
                paths=paths,
                store=MarketplaceStore(paths.registry_file),
                trust=TrustStore({"mock-key": ("approved-publisher-id", key)}),
                host_version="2.9.2",
                platform="win32-x64",
            )
        )
        package = _package(root)
        entry = _entry(package, key)
        app = FastAPI()
        app.include_router(router, prefix="/api")
        client = TestClient(app)
        response = client.post(
            "/api/marketplace/plugins/some-other-plugin/install",
            json={"entry": entry.model_dump(mode="json")},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "MARKETPLACE_REQUEST_INVALID"
        assert response.json()["detail"]["message"] == "Marketplace request could not be completed."

        missing_package = client.post(
            f"/api/marketplace/plugins/{entry.id}/install",
            json={"entry": entry.model_dump(mode="json")},
        )
        assert missing_package.status_code == 400
        assert missing_package.json()["detail"] == {
            "code": "MARKETPLACE_REQUEST_INVALID",
            "message": "Marketplace request could not be completed.",
        }
        assert str(root) not in missing_package.text

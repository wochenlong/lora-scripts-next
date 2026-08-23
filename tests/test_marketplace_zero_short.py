from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import shutil
import socket
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import httpx
import uvicorn

import uuid
from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikazuki.app.api import router as core_api_router
from mikazuki.plugin_host import AgentRouteAuthorityConfig
from mikazuki.plugin_host.runtime import ExecutablePluginRuntime
from mikazuki.plugin_marketplace.api import (
    configure_marketplace,
    configure_marketplace_authority,
    host_router,
)
from mikazuki.plugin_marketplace.manager import MarketplaceManager
from mikazuki.plugin_marketplace.models import MarketplaceEntry
from mikazuki.plugin_marketplace.package import inspect_package
from mikazuki.plugin_marketplace.paths import MarketplacePaths
from mikazuki.plugin_marketplace.store import MarketplaceStore
from mikazuki.plugin_marketplace.trust import TrustStore, canonical_entry_payload


PLUGIN_ID = "next-trainer-pi-agent"
HOST_VERSION = "2.9.2"
PLATFORM = "win32-x64"
SIGNING_KEY_ID = "zero-short-test"
SIGNING_KEY = b"zero-short-test-signing-key"
PACKAGE_ROOT = Path(__file__).parents[1] / "plugin-packages" / PLUGIN_ID


def _package(root: Path, *, version: str, executable: bytes | None = None) -> Path:
    manifest = json.loads((PACKAGE_ROOT / "plugin.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    package = root / f"{PLUGIN_ID}-{version}.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
        sidecar = PACKAGE_ROOT / "dist" / "bin" / "next-trainer-pi-agent.exe"
        archive.writestr(
            "bin/next-trainer-pi-agent.exe",
            sidecar.read_bytes() if executable is None else executable,
        )
        archive.write(PACKAGE_ROOT / "dist" / "ui" / "index.html", "ui/index.html")
        archive.write(PACKAGE_ROOT / "dist" / "ui" / "index.js", "ui/index.js")
        archive.write(PACKAGE_ROOT / "dist" / "ui" / "settings.html", "ui/settings.html")
        archive.write(PACKAGE_ROOT / "sbom.cdx.json", "sbom.cdx.json")
        archive.write(PACKAGE_ROOT / "LICENSES" / "MIT.txt", "LICENSE")
        archive.write(PACKAGE_ROOT / "LICENSES" / "MIT.txt", "LICENSES/MIT.txt")
    return package


def _entry(package: Path, *, version: str) -> MarketplaceEntry:
    manifest = json.loads((PACKAGE_ROOT / "plugin.json").read_text(encoding="utf-8"))
    value = {
        "id": PLUGIN_ID,
        "name": "Next Trainer Pi Agent",
        "publisher_id": manifest["publisher"],
        "description": "Optional Pi Agent",
        "latest_version": version,
        "channel": "stable",
        "host_compatibility": manifest["hostCompatibility"],
        "platforms": manifest["platforms"],
        "package_size": package.stat().st_size,
        "permissions_summary": manifest["permissions"],
        "license": "MIT",
        "package_url": "https://market.invalid/next-trainer-pi-agent.zip",
        "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "signing_key_id": SIGNING_KEY_ID,
        "published_at": "2026-08-22T00:00:00Z",
        "signature": "",
    }
    entry = MarketplaceEntry.model_validate(value)
    value["signature"] = hmac.new(SIGNING_KEY, canonical_entry_payload(entry), hashlib.sha256).hexdigest()
    return MarketplaceEntry.model_validate(value)


@contextmanager
def _workspace_tempdir(prefix: str):
    """Workspace-local temp root for the real-package Zero-Short flow.

    Under the DSH file sandbox, monitored child processes (python) cannot
    create files inside ``tempfile.mkdtemp`` directories, neither in the
    redirected platform temp area nor in the workspace.  Plain ``os.mkdir``
    directories under the workspace remain writable, so this verifier uses a
    workspace-local root instead.  Product assertions are unchanged.
    """
    base = Path(__file__).resolve().parents[1] / ".runtime" / "pytest-tmp"
    base.mkdir(parents=True, exist_ok=True)
    root = base / f"{prefix}{uuid.uuid4().hex[:10]}"
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_fresh_package_marketplace_zero_short_real_sidecar_and_core_survival():
    """Exercise the real dist package through manager/runtime lifecycle from empty state."""
    assert (PACKAGE_ROOT / "dist" / "bin" / "next-trainer-pi-agent.exe").is_file(), "build sidecar first"
    assert (PACKAGE_ROOT / "dist" / "ui" / "index.js").is_file(), "build UI first"

    with _workspace_tempdir("next-trainer-zero-short-") as root:
        package_v1 = _package(root, version="0.1.0")
        paths = MarketplacePaths(root / "marketplace")
        runtime = ExecutablePluginRuntime(startup_timeout=30)
        manager = MarketplaceManager(
            paths=paths,
            store=MarketplaceStore(paths.registry_file),
            trust=TrustStore({SIGNING_KEY_ID: ("next-trainer-project", SIGNING_KEY)}),
            host_version=HOST_VERSION,
            platform=PLATFORM,
            runtime=runtime,
        )

        # Empty core/plugin state before install.
        assert manager.status(PLUGIN_ID).state == "not_installed"
        manifest, _ = inspect_package(package_v1, manager.package_limits)
        assert manifest.version == "0.1.0"
        installed = manager.install(_entry(package_v1, version="0.1.0"), package_v1)
        assert installed.state == "installed"
        assert installed.enabled is False

        enabled = manager.enable(PLUGIN_ID, set(manifest.permissions))
        assert enabled.enabled is True
        assert enabled.runtime_state == "running"

        request_id = "6f8b9f6a-8e6d-4b6a-9e8c-6d8f8d5b2f1a"
        bridge_data = asyncio.run(runtime.request(PLUGIN_ID, request_id, "session.list", {}))
        assert isinstance(bridge_data, list)
        providers = asyncio.run(runtime.request(PLUGIN_ID, "7a9f9a5b-3a73-4e35-98d4-5a5f4b3a2d1c", "provider.list", {}))
        assert isinstance(providers, list)

        # Exercise the real Host HTTP seam against the same running sidecar.
        # The Agent route authority requires a genuine loopback client, so the
        # seam runs on a real uvicorn socket instead of the TestClient
        # transport (whose virtual client is not a loopback address).
        app = FastAPI()
        app.include_router(host_router, prefix="/api")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            app_port = sock.getsockname()[1]
        host = f"127.0.0.1:{app_port}"
        origin = f"http://{host}"
        run_token = "zero-short-host-run-token"
        configure_marketplace(manager)
        configure_marketplace_authority(
            AgentRouteAuthorityConfig(
                allowed_hosts={host},
                allowed_origins={origin},
                run_token=run_token,
            )
        )
        headers = {
            "Origin": origin,
            "Sec-Fetch-Site": "same-origin",
            "X-NextTrainer-Run-Token": run_token,
        }
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=app_port, log_level="error"))
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        try:
            deadline = time.time() + 20
            while not server.started and time.time() < deadline:
                time.sleep(0.05)
            assert server.started, "uvicorn did not start"
            with httpx.Client(base_url=origin, headers=headers, timeout=30.0) as client:
                bootstrap = client.post("/api/plugin-host/bootstrap", json={})
                assert bootstrap.status_code == 200
                assert bootstrap.json()["data"]["header"] == "X-NextTrainer-Run-Token"
                extensions = client.get("/api/plugin-host/extensions")
                assert extensions.status_code == 200
                assert extensions.json()["data"]["extensions"][0]["pluginId"] == PLUGIN_ID
                asset = client.get(f"/api/plugin-host/ui/{PLUGIN_ID}/0.1.0/index.html")
                assert asset.status_code == 200
                assert "default-src 'none'" in asset.headers["content-security-policy"]
                host_request = client.post(
                    f"/api/plugin-host/extensions/{PLUGIN_ID}/requests",
                    json={"requestId": "b8fbe2f1-84d0-4c53-8fc6-7f7c53e16b2d", "method": "session.list", "params": {}},
                )
                assert host_request.status_code == 200
                assert host_request.json()["ok"] is True
                assert isinstance(host_request.json()["data"], list)
        finally:
            server.should_exit = True
            server_thread.join(timeout=10)

        # A malformed executable is a genuinely bad update. The active healthy
        # version must remain enabled and running after update rollback.
        package_bad = _package(root, version="0.2.0", executable=b"not-a-windows-executable")
        try:
            manager.install(_entry(package_bad, version="0.2.0"), package_bad)
        except RuntimeError:
            pass
        else:
            raise AssertionError("bad update unexpectedly succeeded")
        after_bad_update = manager.status(PLUGIN_ID)
        assert after_bad_update.active_version == "0.1.0"
        assert after_bad_update.enabled is True
        assert after_bad_update.runtime_state == "running"

        disabled = manager.disable(PLUGIN_ID)
        assert disabled.enabled is False
        assert disabled.runtime_state == "stopped"
        assert manager.status(PLUGIN_ID).state == "installed"

        user_data = paths.user_data_dir(PLUGIN_ID)
        user_data.mkdir(parents=True, exist_ok=True)
        (user_data / "auth.json").write_text("{}", encoding="utf-8")
        removed = manager.uninstall(PLUGIN_ID)
        assert removed.state == "not_installed"
        assert user_data.is_dir(), "ordinary uninstall must preserve plugin user data"
        assert not paths.plugin_root(PLUGIN_ID).exists()

        # The host's core API remains usable after the optional plugin is gone.
        core = FastAPI()
        core.include_router(core_api_router, prefix="/api")
        with TestClient(core) as client:
            response = client.get("/api/version")
            assert response.status_code == 200
            assert response.json()["status"] == "success"

        shutil.rmtree(user_data)

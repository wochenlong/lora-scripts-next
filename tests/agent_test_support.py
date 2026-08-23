"""Shared helpers for the real-stack Agent verifiers (Zero-Short, vertical chain, EDD).

These helpers build the signed mock package from the real dist artifacts and
run the FastAPI Agent routes on a genuine loopback socket (the Agent route
authority requires a real loopback client, so the TestClient transport is not
usable for ``/api/plugin-host`` and ``/api/internal/agent-tools``).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import socket
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI

from mikazuki.app.api import router as core_api_router
from mikazuki.plugin_host import AgentRouteAuthorityConfig
from mikazuki.plugin_marketplace.api import (
    configure_marketplace,
    configure_marketplace_authority,
)
from mikazuki.plugin_marketplace.models import MarketplaceEntry
from mikazuki.plugin_marketplace.package import inspect_package
from mikazuki.plugin_marketplace.trust import canonical_entry_payload

PLUGIN_ID = "next-trainer-pi-agent"
HOST_VERSION = "2.9.2"
PLATFORM = "win32-x64"
SIGNING_KEY_ID = "agent-test-signing"
SIGNING_KEY = b"agent-test-signing-key"
PACKAGE_ROOT = Path(__file__).parents[1] / "plugin-packages" / PLUGIN_ID


@contextmanager
def workspace_tempdir(prefix: str):
    """Workspace-local temp root (DSH sandbox denies writes to mkdtemp dirs)."""
    base = Path(__file__).resolve().parents[1] / ".runtime" / "pytest-tmp"
    base.mkdir(parents=True, exist_ok=True)
    root = base / f"{prefix}{uuid.uuid4().hex[:10]}"
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def dev_docs_root() -> Path:
    """Locate the development-docs workspace root across layouts.

    MIKAZUKI_DEV_DOCS overrides both. The canonical source workspace keeps
    the docs in the sibling directory lora-scripts-next-agent-development-docs;
    the isolated backup keeps development-docs next to the repository copy.
    """
    override = os.environ.get("MIKAZUKI_DEV_DOCS", "").strip()
    if override:
        return Path(override)
    here = Path(__file__).resolve().parent  # tests/
    parent = here.parents[0]  # repository root
    candidates = [
        parent.parent / "lora-scripts-next-agent-development-docs",
        parent.parent / "development-docs",
        parent / "development-docs",
    ]
    for candidate in candidates:
        if (candidate / "00_预检证据").is_dir() or (candidate / "evidence").is_dir():
            return candidate
    return candidates[0]


def build_package(root: Path, *, version: str = "0.1.0", executable: bytes | None = None, permissions: list[str] | None = None, drop_bridge_permissions: set[str] | None = None) -> Path:
    manifest = json.loads((PACKAGE_ROOT / "plugin.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    if permissions is not None:
        manifest["permissions"] = list(permissions)
    if drop_bridge_permissions:
        bridge = manifest.setdefault("bridge", {})
        for section in ("requests", "streams"):
            bridge[section] = [
                item for item in bridge.get(section, [])
                if item.get("permission") not in drop_bridge_permissions
            ]
    package = root / f"{PLUGIN_ID}-{version}.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
        archive.writestr(
            "bin/next-trainer-pi-agent.exe",
            executable if executable is not None else (PACKAGE_ROOT / "dist" / "bin" / "next-trainer-pi-agent.exe").read_bytes(),
        )
        for name in ("index.html", "index.js", "index.css", "settings.html"):
            archive.write(PACKAGE_ROOT / "dist" / "ui" / name, f"ui/{name}")
        archive.write(PACKAGE_ROOT / "sbom.cdx.json", "sbom.cdx.json")
        archive.write(PACKAGE_ROOT / "LICENSES" / "MIT.txt", "LICENSE")
        archive.write(PACKAGE_ROOT / "LICENSES" / "MIT.txt", "LICENSES/MIT.txt")
    return package


def build_entry(package: Path, *, version: str = "0.1.0", signing_key_id: str = SIGNING_KEY_ID, signing_key: bytes = SIGNING_KEY, permissions: list[str] | None = None) -> MarketplaceEntry:
    manifest = json.loads((PACKAGE_ROOT / "plugin.json").read_text(encoding="utf-8"))
    if permissions is not None:
        manifest["permissions"] = list(permissions)
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
        "package_url": f"https://market.invalid/{PLUGIN_ID}.zip",
        "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "signing_key_id": signing_key_id,
        "published_at": "2026-08-23T00:00:00Z",
        "signature": "",
    }
    entry = MarketplaceEntry.model_validate(value)
    value["signature"] = hmac.new(signing_key, canonical_entry_payload(entry), hashlib.sha256).hexdigest()
    return MarketplaceEntry.model_validate(value)


class HostApp:
    """Run the real FastAPI Agent host on a loopback socket."""

    def __init__(self, manager, *, run_token: str, port: int | None = None) -> None:
        self.app_port = port if port is not None else free_port()
        self.host = f"127.0.0.1:{self.app_port}"
        self.origin = f"http://{self.host}"
        self.run_token = run_token
        self.manager = manager
        app = FastAPI()
        app.include_router(core_api_router, prefix="/api")
        configure_marketplace(manager)
        configure_marketplace_authority(
            AgentRouteAuthorityConfig(
                allowed_hosts={self.host},
                allowed_origins={self.origin},
                run_token=run_token,
            )
        )
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.app_port, log_level="error"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> "HostApp":
        self.thread.start()
        deadline = time.time() + 20
        while not self.server.started and time.time() < deadline:
            time.sleep(0.05)
        if not self.server.started:
            raise RuntimeError("uvicorn did not start")
        return self

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)

    def client(self, timeout: float = 60.0) -> httpx.Client:
        return httpx.Client(
            base_url=self.origin,
            headers={
                "Origin": self.origin,
                "Sec-Fetch-Site": "same-origin",
                "X-NextTrainer-Run-Token": self.run_token,
            },
            timeout=timeout,
        )

    def bridge_request(self, client: httpx.Client, method: str, params: dict) -> dict:
        response = client.post(
            f"/api/plugin-host/extensions/{PLUGIN_ID}/requests",
            json={"requestId": str(uuid.uuid4()), "method": method, "params": params},
        )
        assert response.status_code == 200, (method, response.text)
        payload = response.json()
        assert payload.get("ok") is True, (method, payload)
        return payload["data"]

    def bridge_error(self, client: httpx.Client, method: str, params: dict) -> tuple[int, dict]:
        response = client.post(
            f"/api/plugin-host/extensions/{PLUGIN_ID}/requests",
            json={"requestId": str(uuid.uuid4()), "method": method, "params": params},
        )
        payload = response.json()
        assert payload.get("ok") is False, (method, payload)
        return response.status_code, payload["error"]

    def catalog(self, client: httpx.Client, token: str) -> tuple[int, dict]:
        response = client.get("/api/internal/agent-tools/definitions", headers={"Authorization": f"Bearer {token}"})
        return response.status_code, response.json()

    def host_tool(self, client: httpx.Client, token: str, tool: str, arguments: dict, *, session_id: str = "edd-session", tool_call_id: str | None = None) -> tuple[int, dict]:
        # Header names must match the sidecar's wire format exactly. httpx 0.24.1
        # mangles mixed-case header names on the wire (dashes are stripped), so
        # the all-lowercase dashed names are used here as sent by the sidecar.
        headers = {
            "Authorization": f"Bearer {token}",
            "x-next-trainer-session-id": session_id,
            "x-next-trainer-tool-call-id": tool_call_id or str(uuid.uuid4()),
        }
        response = client.post(f"/api/internal/agent-tools/{tool}", json={"arguments": arguments}, headers=headers)
        return response.status_code, response.json()


def require_dist() -> None:
    assert (PACKAGE_ROOT / "dist" / "bin" / "next-trainer-pi-agent.exe").is_file(), "build sidecar first"
    assert (PACKAGE_ROOT / "dist" / "ui" / "index.js").is_file(), "build UI first"

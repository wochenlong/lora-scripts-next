"""Real vertical chain: FastAPI Host routes -> capability broker -> real sidecar
EXE -> real Pi 0.84.2 runtime (fake local Provider) -> real UI bundle.

Unlike the marketplace Zero-Short verifier, this test drives every
browser-side operation through real HTTP against a running FastAPI
application (uvicorn on a real loopback port), including the SSE event
stream, and closes one agent prompt to its terminal state
(``prompt_done`` / ``agent_settled``) exactly as the UI would observe it.
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI

from mikazuki.app.api import router as core_api_router
from mikazuki.plugin_host import AgentRouteAuthorityConfig
from mikazuki.plugin_host.runtime import ExecutablePluginRuntime
from mikazuki.plugin_marketplace.api import (
    configure_marketplace,
    configure_marketplace_authority,
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
SIGNING_KEY_ID = "vertical-chain-test"
SIGNING_KEY = b"vertical-chain-test-signing-key"
API_KEY = "sk-vertical-chain-secret"
ANSWER = "vertical-chain-ok"
PACKAGE_ROOT = Path(__file__).parents[1] / "plugin-packages" / PLUGIN_ID
EXPECTED_HOST_TOOLS = frozenset(
    {
        "training_config_template",
        "training_config_validate",
        "training_config_commit",
        "dataset_inventory",
        "dataset_review_images",
        "dataset_caption_stage",
        "dataset_caption_commit",
        "knowledge_search",
        "civitai_search_loras",
        "civitai_cohort_report",
        "curve_analyze",
        "artifact_compare",
        "artifact_recommend",
    }
)


class _FakeChatHandler(BaseHTTPRequestHandler):
    """OpenAI-compatible /v1/chat/completions endpoint returning one SSE completion."""

    requests: list = []

    def log_message(self, *args):  # keep test output quiet
        pass

    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        _FakeChatHandler.requests.append(
            {
                "url": self.path,
                "authorization": self.headers.get("authorization"),
                "body": json.loads(body.decode("utf8")),
            }
        )
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        chunks = [
            {
                "id": "chatcmpl-v1",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "vertical-test-model",
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
            },
            {
                "id": "chatcmpl-v1",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "vertical-test-model",
                "choices": [{"index": 0, "delta": {"content": ANSWER}, "finish_reason": None}],
            },
            {
                "id": "chatcmpl-v1",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "vertical-test-model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            },
        ]
        for chunk in chunks:
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf8"))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


@contextmanager
def _workspace_tempdir(prefix: str):
    """Workspace-local temp root (see test_marketplace_zero_short for rationale)."""
    base = Path(__file__).resolve().parents[1] / ".runtime" / "pytest-tmp"
    base.mkdir(parents=True, exist_ok=True)
    root = base / f"{prefix}{uuid.uuid4().hex[:10]}"
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _package(root: Path, *, version: str) -> Path:
    manifest = json.loads((PACKAGE_ROOT / "plugin.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    package = root / f"{PLUGIN_ID}-{version}.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
        archive.writestr(
            "bin/next-trainer-pi-agent.exe",
            (PACKAGE_ROOT / "dist" / "bin" / "next-trainer-pi-agent.exe").read_bytes(),
        )
        for name in ("index.html", "index.js", "index.css", "settings.html"):
            archive.write(PACKAGE_ROOT / "dist" / "ui" / name, f"ui/{name}")
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
        "published_at": "2026-08-23T00:00:00Z",
        "signature": "",
    }
    entry = MarketplaceEntry.model_validate(value)
    value["signature"] = hmac.new(SIGNING_KEY, canonical_entry_payload(entry), hashlib.sha256).hexdigest()
    return MarketplaceEntry.model_validate(value)


def test_fastapi_host_sidecar_pi_ui_real_vertical_chain():
    assert (PACKAGE_ROOT / "dist" / "bin" / "next-trainer-pi-agent.exe").is_file(), "build sidecar first"
    assert (PACKAGE_ROOT / "dist" / "ui" / "index.js").is_file(), "build UI first"

    with _workspace_tempdir("next-trainer-vertical-") as root:
        _run_vertical_chain(root)


def _run_vertical_chain(root: Path):
    _FakeChatHandler.requests = []
    provider = ThreadingHTTPServer(("127.0.0.1", 0), _FakeChatHandler)
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    provider_endpoint = f"http://127.0.0.1:{provider.server_address[1]}/v1/chat/completions"

    app_port = _free_port()
    host = f"127.0.0.1:{app_port}"
    origin = f"http://{host}"
    run_token = "vertical-chain-host-run-token"

    # Verifier-only escape hatch so the real EXE accepts the local fake
    # Provider endpoint; production hosts never set this variable.
    os.environ["NEXT_TRAINER_ALLOW_HTTP_LOOPBACK"] = "1"
    server = None
    server_thread = None
    try:
        package_v1 = _package(root, version="0.1.0")
        paths = MarketplacePaths(root / "marketplace")
        runtime = ExecutablePluginRuntime(
            startup_timeout=30,
            host_tool_base_url=f"http://127.0.0.1:{app_port}/api",
        )
        manager = MarketplaceManager(
            paths=paths,
            store=MarketplaceStore(paths.registry_file),
            trust=TrustStore({SIGNING_KEY_ID: ("next-trainer-project", SIGNING_KEY)}),
            host_version=HOST_VERSION,
            platform=PLATFORM,
            runtime=runtime,
        )

        app = FastAPI()
        app.include_router(core_api_router, prefix="/api")
        configure_marketplace(manager)
        configure_marketplace_authority(
            AgentRouteAuthorityConfig(
                allowed_hosts={host},
                allowed_origins={origin},
                run_token=run_token,
            )
        )
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=app_port, log_level="error"))
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        deadline = time.time() + 20
        while not server.started and time.time() < deadline:
            time.sleep(0.05)
        assert server.started, "uvicorn did not start"

        manifest, _ = inspect_package(package_v1, manager.package_limits)
        installed = manager.install(_entry(package_v1, version="0.1.0"), package_v1)
        assert installed.state == "installed"
        enabled = manager.enable(PLUGIN_ID, set(manifest.permissions))
        assert enabled.enabled is True
        assert enabled.runtime_state == "running"

        headers = {
            "Origin": origin,
            "Sec-Fetch-Site": "same-origin",
            "X-NextTrainer-Run-Token": run_token,
        }
        with httpx.Client(base_url=origin, headers=headers, timeout=60.0) as client:
            bootstrap = client.post("/api/plugin-host/bootstrap", json={})
            assert bootstrap.status_code == 200
            assert bootstrap.json()["data"]["header"] == "X-NextTrainer-Run-Token"

            extensions = client.get("/api/plugin-host/extensions")
            assert extensions.status_code == 200
            extension = extensions.json()["data"]["extensions"][0]
            assert extension["pluginId"] == PLUGIN_ID
            assert "session.subscribe" in extension["capabilities"]

            # The real UI bundle is served by the host with a locked CSP.
            for asset in ("index.html", "index.js", "index.css", "settings.html"):
                page = client.get(f"/api/plugin-host/ui/{PLUGIN_ID}/0.1.0/{asset}")
                assert page.status_code == 200, asset
                assert "default-src 'none'" in page.headers.get("content-security-policy", ""), asset
            index_js = client.get(f"/api/plugin-host/ui/{PLUGIN_ID}/0.1.0/index.js")
            assert len(index_js.content) > 100_000, "served index.js is not the real bundle"

            def bridge_request(method: str, params: dict) -> dict:
                response = client.post(
                    f"/api/plugin-host/extensions/{PLUGIN_ID}/requests",
                    json={"requestId": str(uuid.uuid4()), "method": method, "params": params},
                )
                assert response.status_code == 200, (method, response.text)
                payload = response.json()
                assert payload.get("ok") is True, (method, payload)
                return payload["data"]

            saved = bridge_request(
                "provider.saveKey",
                {
                    "profileId": "vertical-dev",
                    "modelId": "vertical-test-model",
                    "endpoint": provider_endpoint,
                    "key": API_KEY,
                },
            )
            assert saved["configured"] is True
            assert API_KEY not in json.dumps(saved), "provider status must not expose the raw key"

            session = bridge_request(
                "session.create",
                {"model": {"profileId": "vertical-dev", "modelId": "vertical-test-model"}, "name": "vertical-chain"},
            )
            session_id = session["id"]
            assert session.get("name") == "vertical-chain"

            listed = bridge_request("session.list", {})
            assert any(item.get("name") == "vertical-chain" for item in listed)

            events: list = []
            stream_error: dict = {}

            def consume_stream():
                try:
                    with client.stream(
                        "POST",
                        f"/api/plugin-host/extensions/{PLUGIN_ID}/streams",
                        json={
                            "requestId": str(uuid.uuid4()),
                            "method": "session.subscribe",
                            "params": {"sessionId": session_id},
                        },
                        timeout=httpx.Timeout(120.0, read=120.0),
                    ) as stream:
                        for line in stream.iter_lines():
                            if not line.startswith("data:"):
                                continue
                            envelope = json.loads(line[5:].strip())
                            if envelope.get("ok") is False:
                                stream_error["value"] = envelope
                                return
                            data = envelope.get("data")
                            if isinstance(data, dict):
                                events.append(data)
                                if data.get("type") == "agent_settled":
                                    return
                except Exception as exc:  # noqa: BLE001 - surface any transport failure
                    stream_error["value"] = repr(exc)

            stream_thread = threading.Thread(target=consume_stream, daemon=True)
            stream_thread.start()
            time.sleep(0.5)  # let the SSE subscription attach before the prompt

            receipt = bridge_request(
                "session.prompt",
                {
                    "sessionId": session_id,
                    "input": {"text": f"Reply with exactly: {ANSWER}", "clientSubmissionId": str(uuid.uuid4())},
                },
            )
            assert receipt["accepted"] is True
            assert receipt["sessionId"] == session_id

            stream_thread.join(timeout=90)
            assert not stream_thread.is_alive(), (
                f"stream did not reach terminal state; error={stream_error} last={events[-3:] if events else None}"
            )
            assert not stream_error, stream_error

            types = [event.get("type") for event in events]
            for expected in ("message_start", "message_end", "prompt_done", "agent_settled"):
                assert expected in types, (expected, types)
            settled = next(event for event in events if event.get("type") == "agent_settled")
            assert settled["payload"]["stopReason"] == "stop"
            done = next(event for event in events if event.get("type") == "prompt_done")
            assert done["payload"]["ok"] is True

            # Host custom Tools crossed the whole chain: the LLM request must
            # carry the host tool catalog (and none of the builtin tools).
            assert _FakeChatHandler.requests, "fake Provider was never called"
            tool_names = set()
            for request in _FakeChatHandler.requests:
                assert request["url"] == "/v1/chat/completions", request["url"]
                assert request["authorization"] == f"Bearer {API_KEY}"
                for tool in request["body"].get("tools") or []:
                    tool_names.add(tool["function"]["name"])
            assert tool_names == EXPECTED_HOST_TOOLS, tool_names

            events_json = json.dumps(events, ensure_ascii=False)
            assert API_KEY not in events_json, "provider key leaked into UI events"
            assert ANSWER in events_json

            history = bridge_request("session.getHistory", {"sessionId": session_id, "limit": 50})
            history_json = json.dumps(history, ensure_ascii=False)
            assert ANSWER in history_json
            assert API_KEY not in history_json

            # The real Pi runtime persisted a JSONL session inside the
            # plugin-isolated data root, without credential material.
            sessions_dir = paths.user_data_dir(PLUGIN_ID) / "pi-agent" / "sessions"
            jsonl_files = list(sessions_dir.glob("*.jsonl"))
            assert jsonl_files, "no Pi JSONL session was persisted"
            persisted = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in jsonl_files)
            assert ANSWER in persisted
            assert API_KEY not in persisted

            # Core product API stays healthy while the optional plugin runs.
            version = client.get("/api/version")
            assert version.status_code == 200
            assert version.json()["status"] == "success"

        disabled = manager.disable(PLUGIN_ID)
        assert disabled.enabled is False
        assert disabled.runtime_state == "stopped"
        assert runtime.status(PLUGIN_ID).state == "stopped"
    finally:
        os.environ.pop("NEXT_TRAINER_ALLOW_HTTP_LOOPBACK", None)
        if server is not None:
            server.should_exit = True
        if server_thread is not None:
            server_thread.join(timeout=10)
        provider.shutdown()
        shutil.rmtree(root, ignore_errors=True)

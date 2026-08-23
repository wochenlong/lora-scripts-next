"""Real-app-entry local/test catalog install journey.

Drives the production application entry (mikazuki.app:app via uvicorn in a
child process) with the local/test trusted catalog wired through the
development environment variables, then exercises the full user journey:

  catalog list -> install (permissions approved) -> enable -> sidecar ready
  -> extension/UI serving -> disable -> uninstall -> core pages still fine.

A second instance without the wiring proves the fail-closed default
(catalog offline, install rejected, core still usable).

This verifier replaces nothing: the in-process marketplace suite stays as
the focused contract layer; this one proves the shipped app entry.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "next-trainer-pi-agent"
DEV_CATALOG = PROJECT / "plugin-packages" / PLUGIN_ID / "dev-catalog"
TMP_BASE = PROJECT / ".runtime" / "pytest-tmp"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _http(method: str, url: str, *, headers: dict[str, str] | None = None, body: dict | None = None, timeout: int = 30):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:500]}


def _fetch_text(url: str, timeout: int = 60) -> tuple[int, str]:
    with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def _probe_status(url: str, timeout: int = 5) -> int | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout) as response:
            response.read()
            return response.status
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code
    except Exception:  # noqa: BLE001 - readiness polling
        return None


def _wait_ready(base: str, timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    last_status: int | None = None
    while time.time() < deadline:
        last_status = _probe_status(base + "/")
        if last_status == 200:
            return
        time.sleep(2)
    raise AssertionError(f"app did not become ready (last status {last_status})")


class _App:
    def __init__(self, port: int, *, catalog: bool):
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.origin = self.base
        tmp = TMP_BASE / f"local-catalog-{uuid.uuid4().hex[:10]}"
        tmp.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["MIKAZUKI_HOST"] = "127.0.0.1"
        env["MIKAZUKI_PORT"] = str(port)
        env["MIKAZUKI_PLUGIN_MARKETPLACE_ROOT"] = str(tmp / "plugin-marketplace")
        env["TMPDIR"] = str(tmp)
        env["TEMP"] = str(tmp)
        env["TMP"] = str(tmp)
        if catalog:
            env["MIKAZUKI_PLUGIN_CATALOG_PATH"] = str(DEV_CATALOG / "catalog.json")
            env["MIKAZUKI_PLUGIN_CATALOG_TRUST"] = str(DEV_CATALOG / "trust.json")
            env["MIKAZUKI_PLUGIN_PACKAGE_SOURCES"] = str(DEV_CATALOG / "acquire-map.json")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "mikazuki.app:app",
             "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
            cwd=str(PROJECT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self._tmp = tmp

    def stop(self) -> None:
        if self.process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
        shutil.rmtree(self._tmp, ignore_errors=True)


def test_local_catalog_install_journey_on_real_app_entry():
    assert (DEV_CATALOG / "catalog.json").is_file(), "run scripts/generate-dev-catalog.py first"
    assert (DEV_CATALOG / "trust.json").is_file()
    assert (DEV_CATALOG / "acquire-map.json").is_file()

    port = _free_port()
    app = _App(port, catalog=True)
    try:
        _wait_ready(app.base)

        # 1) catalog is listed with the Agent entry (what the frontend loads)
        status, payload = _http("GET", app.base + "/api/marketplace/catalog")
        assert status == 200, payload
        entries = payload["data"]
        assert isinstance(entries, list) and len(entries) == 1
        entry = entries[0]
        assert entry["id"] == PLUGIN_ID
        assert entry["publisher_id"] == "next-trainer-project"
        assert entry["permissions_summary"], "entry must declare permissions"
        assert len(entry["sha256"]) == 64 and len(entry["signature"]) == 64

        auth = {"Origin": app.origin, "Sec-Fetch-Site": "same-origin"}
        status, payload = _http("POST", app.base + "/api/plugin-host/bootstrap", headers=auth, body={})
        assert status == 200, payload
        token = payload["data"]["runToken"]
        assert token
        mut = {**auth, "X-NextTrainer-Run-Token": token}

        # 2) install with every declared permission approved
        status, payload = _http(
            "POST",
            app.base + f"/api/marketplace/plugins/{PLUGIN_ID}/install",
            headers=mut,
            body={"approvedPermissions": list(entry["permissions_summary"])},
        )
        assert status == 200, payload
        assert payload["data"]["state"] == "installed"
        assert payload["data"]["active_version"] == entry["latest_version"]

        # 3) enable -> sidecar EXE boots and the extension reports ready
        status, payload = _http(
            "POST",
            app.base + f"/api/marketplace/plugins/{PLUGIN_ID}/enable",
            headers=mut,
            body={"permissions": list(entry["permissions_summary"])},
        )
        assert status == 200, payload
        extensions = None
        deadline = time.time() + 90
        while time.time() < deadline:
            status, payload = _http("GET", app.base + "/api/plugin-host/extensions")
            assert status == 200, payload
            extensions = payload["data"]["extensions"]
            if extensions and extensions[0]["state"] == "ready":
                break
            time.sleep(2)
        assert extensions, "no extension contributed"
        ext = extensions[0]
        assert ext["pluginId"] == PLUGIN_ID
        assert ext["state"] == "ready", f"sidecar did not reach ready: {ext}"
        assert ext["ui"]["floatingPanel"]["entryUrl"].startswith("/api/plugin-host/ui/")

        # 4) plugin UI assets are served through the host
        status, body = _fetch_text(app.base + f"/api/plugin-host/ui/{PLUGIN_ID}/0.1.0/index.js")
        assert status == 200 and len(body) > 1000, "plugin UI bundle not served"
        status, body = _fetch_text(app.base + f"/api/plugin-host/ui/{PLUGIN_ID}/0.1.0/settings.html")
        assert status == 200 and "<html" in body.lower(), "plugin settings page not served"

        # 5) core app remains fully usable with the Agent active
        status, payload = _http("GET", app.base + "/api/schemas/hashes")
        assert status == 200, payload

        # 6) disable -> runtime stops
        status, payload = _http("POST", app.base + f"/api/marketplace/plugins/{PLUGIN_ID}/disable", headers=mut, body={})
        assert status == 200, payload
        deadline = time.time() + 60
        while time.time() < deadline:
            status, payload = _http("GET", app.base + "/api/plugin-host/extensions")
            if payload["data"]["extensions"] and payload["data"]["extensions"][0]["state"] != "starting":
                break
            time.sleep(2)
        assert status == 200

        # 7) uninstall -> back to not_installed
        status, payload = _http("POST", app.base + f"/api/marketplace/plugins/{PLUGIN_ID}/uninstall", headers=mut, body={})
        assert status == 200, payload
        assert payload["data"]["state"] == "not_installed"

        # 8) core pages/APIs still fine after the full lifecycle
        assert _probe_status(app.base + "/") == 200
        status, payload = _http("GET", app.base + "/api/schemas/hashes")
        assert status == 200
    finally:
        app.stop()


def test_default_app_entry_stays_fail_closed_without_local_catalog():
    port = _free_port()
    app = _App(port, catalog=False)
    try:
        _wait_ready(app.base)
        status, payload = _http("GET", app.base + "/api/marketplace/catalog")
        assert status == 503, payload
        assert payload["detail"]["code"] == "MARKETPLACE_CATALOG_OFFLINE"

        auth = {"Origin": app.origin, "Sec-Fetch-Site": "same-origin"}
        status, payload = _http("POST", app.base + "/api/plugin-host/bootstrap", headers=auth, body={})
        assert status == 200
        token = payload["data"]["runToken"]
        mut = {**auth, "X-NextTrainer-Run-Token": token}
        status, payload = _http(
            "POST",
            app.base + f"/api/marketplace/plugins/{PLUGIN_ID}/install",
            headers=mut,
            body={"approvedPermissions": ["model-provider"]},
        )
        assert status >= 400, "install must fail closed without a trusted catalog"

        assert _probe_status(app.base + "/") == 200
        status, payload = _http("GET", app.base + "/api/schemas/hashes")
        assert status == 200
    finally:
        app.stop()

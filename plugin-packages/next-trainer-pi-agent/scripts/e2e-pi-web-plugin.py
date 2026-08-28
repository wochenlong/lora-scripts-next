# /// script
# requires-python = ">=3.11"
# ///
"""Goal v9 / CR-011 — S7 end-to-end verification.

Runs the REAL backend (uvicorn, project venv) against the REAL dist package:

  catalog listing -> install -> enable (launcher starts, pi-web boots) ->
  /api/plugin-host/extensions server-mode projection -> GET uiUrl (pi-web
  HTML) -> pi API probe -> core API sanity -> disable (tree removal) ->
  uninstall.

Usage (from project/):
  .venv-dev\\Scripts\\python.exe plugin-packages\\next-trainer-pi-agent\\scripts\\e2e-pi-web-plugin.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DIST = PROJECT_ROOT / "plugin-packages" / "next-trainer-pi-agent" / "dist-marketplace"
PORT = 28001
BASE = f"http://127.0.0.1:{PORT}"
ORIGIN = BASE
HEADERS_ORIGIN = {"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors"}
PLUGIN_ID = "next-trainer-pi-agent"

STEP = "\n=== S7 step ===\n"


def log(message: str) -> None:
    # Windows consoles default to GBK; pi-web logs contain Unicode (✓, …).
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(message.encode(encoding, "replace").decode(encoding, "replace"), flush=True)


def http(method: str, path: str, *, body: dict | None = None, token: str | None = None,
         origin: bool = False, timeout: float = 30.0) -> tuple[int, dict | bytes]:
    headers = {"Content-Type": "application/json"}
    if origin:
        headers.update(HEADERS_ORIGIN)
    if token:
        headers["X-NextTrainer-Run-Token"] = token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            try:
                return response.status, json.loads(payload.decode("utf-8"))
            except json.JSONDecodeError:
                return response.status, payload
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            return exc.code, payload


def data_of(value: dict) -> dict:
    assert isinstance(value, dict) and value.get("status") == "success" and "data" in value, (
        f"unexpected envelope: {str(value)[:300]}"
    )
    return value["data"]


def wait_server() -> None:
    deadline = time.time() + 120
    last = ""
    while time.time() < deadline:
        try:
            code, value = http("GET", "/api/version")
            if code == 200:
                log(f"backend up: {json.dumps(value)[:200]}")
                return
            last = f"{code} {str(value)[:120]}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(1.0)
    raise AssertionError(f"backend did not come up ({last})")


def node_pi_web_processes(scope: Path | None = None) -> int:
    """Count pi-web node processes, optionally restricted to this run's data
    root (other hosts/instances may keep their own pi-web running)."""
    pattern = "pi-web\\\\bin\\\\pi-web\\.js"
    if scope is not None:
        pattern = re.escape(str(scope)) + ".*" + pattern
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | "
         f"Where-Object {{ $_.CommandLine -match '{pattern}' }} | Measure-Object).Count"],
        capture_output=True, text=True,
    )
    return int(result.stdout.strip() or "0")


def main() -> int:
    for required in (DIST / "catalog.json", DIST / "trust.json", DIST / "packages" / f"{PLUGIN_ID}-0.2.0-win32-x64.zip"):
        if not required.is_file():
            raise SystemExit(f"missing artifact: {required}")

    runtime_root = Path(tempfile.mkdtemp(prefix="nt-pi-e2e-"))
    env = os.environ.copy()
    env.update(
        {
            "MIKAZUKI_HOST": "127.0.0.1",
            "MIKAZUKI_PORT": str(PORT),
            "MIKAZUKI_PLUGIN_MARKETPLACE_ROOT": str(runtime_root),
            "MIKAZUKI_MARKETPLACE_CATALOG": str(DIST / "catalog.json"),
            "MIKAZUKI_MARKETPLACE_TRUST": str(DIST / "trust.json"),
            "MIKAZUKI_MARKETPLACE_PACKAGE_ROOT": str(DIST / "packages"),
        }
    )
    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "mikazuki.app.application:app",
            "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    exit_code = 1
    try:
        wait_server()

        log(STEP + "1. core API sanity (pre-install)")
        code, value = http("GET", "/api/version")
        assert code == 200, (code, str(value)[:200])
        log(f"backend version: {json.dumps(value.get('data', {}))[:120]}")

        log(STEP + "2. bootstrap returns a run token")
        code, value = http("POST", "/api/plugin-host/bootstrap", body={}, origin=True)
        assert code == 200, (code, str(value)[:300])
        token = data_of(value)["runToken"]
        assert len(token) >= 32

        log(STEP + "3. catalog refresh verifies the HMAC-signed catalog")
        code, value = http("POST", "/api/marketplace/catalog/refresh", body={}, token=token, origin=True)
        assert code == 200, (code, str(value)[:300])
        log(f"catalog refresh: {json.dumps(data_of(value))[:200]}")

        log(STEP + "4. catalog lists the signed 0.2.0 entry")
        code, value = http("GET", "/api/marketplace/catalog", origin=True)
        assert code == 200, (code, str(value)[:300])
        entries = data_of(value)
        entry = next(e for e in entries if e["id"] == PLUGIN_ID)
        assert entry["latest_version"] == "0.2.0"
        assert entry["permissions_summary"] == []
        log(f"catalog entry: {entry['id']} {entry['latest_version']} size={entry['package_size']}")

        log(STEP + "5. install from the local acquirer (HMAC + sha256 verified, ~1.2GB unpack)")
        # The 305 MB package unpacks ~1.2 GB / 34.5k files server-side;
        # allow a long client timeout for first-run extraction.
        code, value = http("POST", f"/api/marketplace/plugins/{PLUGIN_ID}/install",
                           body={"approvedPermissions": []}, token=token, origin=True, timeout=900.0)
        assert code == 200, (code, str(value)[:400])
        status = data_of(value)
        assert status["state"] == "installed", status
        log(f"installed: {status['state']} active={status['active_version']}")

        log(STEP + "6. enable -> real launcher starts (boot pi-web)")
        code, value = http("POST", f"/api/marketplace/plugins/{PLUGIN_ID}/enable",
                           body={"permissions": []}, token=token, origin=True, timeout=300.0)
        assert code == 200, (code, str(value)[:400])
        status = data_of(value)
        assert status["state"] == "enabled", status
        assert status["runtime_state"] == "running", status
        assert status.get("runtime_ui_url", "").startswith("http://127.0.0.1:"), status
        log(f"enabled: runtime={status['runtime_state']} ui={status.get('runtime_ui_url')}")
        ui_url = status["runtime_ui_url"]
        assert node_pi_web_processes(runtime_root) >= 1, "pi-web node process not running"

        log(STEP + "7. extensions projection is server mode with the live URL")
        code, value = http("GET", "/api/plugin-host/extensions", origin=True)
        assert code == 200, (code, str(value)[:300])
        extensions = data_of(value)["extensions"]
        projection = next(e for e in extensions if e["pluginId"] == PLUGIN_ID)
        panel = projection["ui"]["floatingPanel"]
        assert panel["mode"] == "server", panel
        assert panel["entryUrl"] == ui_url, panel
        assert projection["capabilities"] == []
        log(f"projection: mode={panel['mode']} entry={panel['entryUrl']} state={projection['state']}")

        log(STEP + "8. uiUrl serves the verbatim pi-web UI (cross-origin, direct fetch)")
        try:
            with urllib.request.urlopen(ui_url, timeout=15.0) as response:
                html = response.read().decode("utf-8", errors="replace")
                ui_code = response.status
        except urllib.error.HTTPError as exc:
            ui_code, html = exc.code, exc.read().decode("utf-8", errors="replace")
        assert ui_code == 200, ui_code
        assert len(html) > 1000 and "<html" in html.lower(), f"unexpected body ({len(html)} bytes)"
        log(f"pi-web UI: {ui_code} {len(html)} bytes")

        log(STEP + "9. pi runtime API answers through the live server")
        # The first API call after a cold `next start` can stall while the
        # server finishes warming up; retry with a long timeout and record
        # the timings so a genuine hang stays visible in the evidence.
        attempts = []
        sessions_code, sessions = None, None
        for attempt in (1, 2):
            started = time.time()
            try:
                with urllib.request.urlopen(f"{ui_url}/api/sessions", timeout=90.0) as response:
                    sessions_code = response.status
                    sessions = json.loads(response.read().decode("utf-8"))
                attempts.append(f"attempt{attempt}={time.time() - started:.1f}s/{sessions_code}")
                break
            except urllib.error.HTTPError as exc:
                sessions_code = exc.code
                sessions = json.loads(exc.read().decode("utf-8"))
                attempts.append(f"attempt{attempt}={time.time() - started:.1f}s/{sessions_code}")
                break
            except (TimeoutError, urllib.error.URLError) as exc:
                attempts.append(f"attempt{attempt}={time.time() - started:.1f}s/timeout({type(exc).__name__})")
                continue
        log("timings: " + " ".join(attempts))
        assert sessions_code == 200, (sessions_code, sessions, attempts)
        log(f"pi-web /api/sessions: {sessions_code} {json.dumps(sessions)[:160]}")

        log(STEP + "10. core API sanity (with plugin running)")
        code, _ = http("GET", "/api/version")
        assert code == 200

        log(STEP + "11. disable -> runtime and pi-web tree stop")
        code, value = http("POST", f"/api/marketplace/plugins/{PLUGIN_ID}/disable",
                           body={}, token=token, origin=True, timeout=120.0)
        assert code == 200, (code, str(value)[:300])
        status = data_of(value)
        assert status["enabled"] is False and status["runtime_state"] in ("stopped", None), status
        deadline = time.time() + 30
        while time.time() < deadline and node_pi_web_processes(runtime_root) > 0:
            time.sleep(1.0)
        assert node_pi_web_processes(runtime_root) == 0, "pi-web process survived disable"
        log("disable: runtime stopped, pi-web tree removed")

        log(STEP + "12. uninstall -> not_installed")
        code, value = http("POST", f"/api/marketplace/plugins/{PLUGIN_ID}/uninstall",
                           body={}, token=token, origin=True, timeout=120.0)
        assert code == 200, (code, str(value)[:300])
        status = data_of(value)
        assert status["state"] == "not_installed", status
        log("uninstalled")

        exit_code = 0
        log("\nS7 E2E: ALL STEPS PASSED")
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
        output = server.stdout.read() if server.stdout else ""
        if output:
            log(f"--- backend log tail ---\n{output[-3000:]}")
        # Surface what the embedded pi-web saw (launcher pipes its stdout to
        # <dataRoot>/pi-web.log inside the e2e runtime root).
        for name in ("pi-web.log", "launcher.log"):
            found = [p for p in runtime_root.rglob(name)]
            for path in found[:1]:
                try:
                    tail = path.read_text(encoding="utf-8", errors="replace")[-2500:]
                except OSError:
                    continue
                if tail.strip():
                    log(f"--- {name} tail ({path}) ---\n{tail}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

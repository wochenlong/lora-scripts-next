"""P1-1 crash-bounded auto-restart: an unexpected sidecar exit while the
plugin is still enabled is restarted automatically within a bounded budget
(rolling window, exponential-ish backoff, stable-run reset) instead of
staying crashed until a human intervenes. Budget exhaustion must land in
``crashed`` with an honest snapshot (crash count + last error), never in a
silent restart loop.

Harness: ``ExecutablePluginRuntime._spawn_process`` is overridden to launch
a small Python fake sidecar (READY line + /health server, same wire contract
as the real launcher). The fake can crash on demand via a control file or
after a fixed lifetime, which keeps the tests deterministic and fast.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from mikazuki.plugin_host.runtime import ExecutablePluginRuntime, RuntimeSnapshot

# ---------------------------------------------------------------------------
# Fake sidecar (runs as its own python process)
# ---------------------------------------------------------------------------


def _sidecar_script(crash_file: Path, *, exit_after_seconds: float | None = None, exit_code: int = 9, unhealthy_after_seconds: float | None = None) -> str:
    """Build the fake sidecar's source with the behavior baked in as literals
    (the launch environment is deliberately stripped, so no env is passed)."""
    return f"""
import json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CRASH_FILE = {str(crash_file)!r}
EXIT_AFTER = {exit_after_seconds!r}
EXIT_CODE = {exit_code!r}
UNHEALTHY_AFTER = {unhealthy_after_seconds!r}
BOOT_MONOTONIC = time.monotonic()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            if UNHEALTHY_AFTER is not None and time.monotonic() - BOOT_MONOTONIC >= UNHEALTHY_AFTER:
                self.send_response(500)
                self.end_headers()
                return
            body = json.dumps({{"ok": True, "data": {{"status": "ok", "protocolVersion": "1"}}}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()
print(json.dumps({{"type": "READY", "host": "127.0.0.1", "port": port, "protocolVersion": "1"}}), flush=True)
deadline = time.monotonic() + EXIT_AFTER if EXIT_AFTER else None
while True:
    time.sleep(0.05)
    if os.path.exists(CRASH_FILE):
        try:
            os.remove(CRASH_FILE)  # one-shot: the trigger fires exactly once
        except OSError:
            pass
        os._exit(7)
    if deadline is not None and time.monotonic() >= deadline:
        os._exit(EXIT_CODE)
"""


class _FakeManifest:
    id = "fake-plugin"
    version = "0.1.0"
    protocol_version = "1"

    @property
    def runtime(self):
        class _R:
            entrypoint = "bin/fake-sidecar.exe"

        return _R()


class _SupervisedFakeRuntime(ExecutablePluginRuntime):
    """Real ExecutablePluginRuntime (supervisor included) with the Popen seam
    replaced by the fake sidecar."""

    def __init__(self, script: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._script = script
        self.spawn_count = 0
        self._spawn_lock = threading.Lock()

    def _spawn_process(self, executable, data_root, child_env):
        with self._spawn_lock:
            self.spawn_count += 1
        return subprocess.Popen(
            [sys.executable, "-c", self._script],
            cwd=str(data_root),
            env=dict(child_env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )


def _make_runtime(tmp_path: Path, *, crash_file: Path, **kwargs) -> tuple[_SupervisedFakeRuntime, _FakeManifest, Path, Path]:
    kwargs.setdefault("crash_backoff_seconds", (0.15, 0.2, 0.25))
    kwargs.setdefault("crash_window_seconds", 600.0)
    kwargs.setdefault("crash_stable_reset_seconds", 300.0)
    kwargs.setdefault("supervisor_poll_seconds", 0.05)
    kwargs.setdefault("startup_timeout", 15.0)
    kwargs.setdefault("ui_ready_timeout", 5.0)
    package_root = tmp_path / "package"
    (package_root / "bin").mkdir(parents=True)
    (package_root / "bin" / "fake-sidecar.exe").write_bytes(b"never executed; spawn is overridden")
    data_root = tmp_path / "data"
    runtime = _SupervisedFakeRuntime(_sidecar_script(crash_file, **{k: kwargs.pop(k) for k in ("exit_after_seconds", "exit_code", "unhealthy_after_seconds") if k in kwargs}), **kwargs)
    return runtime, _FakeManifest(), package_root, data_root


def _wait_for(
    runtime: ExecutablePluginRuntime,
    plugin_id: str,
    predicate,
    timeout: float = 12.0,
    interval: float = 0.05,
) -> list[RuntimeSnapshot]:
    deadline = time.monotonic() + timeout
    seen: list[RuntimeSnapshot] = []
    while True:
        snap = runtime.status(plugin_id)
        seen.append(snap)
        if predicate(snap):
            return seen
        if time.monotonic() >= deadline:
            states = [f"{s.state}(pid={s.pid})" for s in seen[-12:]]
            raise AssertionError(f"timed out waiting for status predicate; last={seen[-1].state!r} reason={snap.reason!r}; recent={states}")
        time.sleep(interval)


def _trigger_crash(crash_file: Path) -> None:
    crash_file.write_text("crash", encoding="utf-8")


# ---------------------------------------------------------------------------
# T1: crash -> bounded auto-restart -> READY recovery
# ---------------------------------------------------------------------------


def test_crash_triggers_bounded_auto_restart_and_recovers(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG, logger="mikazuki.plugin_host.runtime")
    crash_file = tmp_path / "crash"
    runtime, manifest, package_root, data_root = _make_runtime(tmp_path, crash_file=crash_file)
    try:
        first = runtime.start(manifest, package_root, data_root)
        assert first.state == "running"
        assert runtime.spawn_count == 1

        _trigger_crash(crash_file)
        seen = _wait_for(runtime, "fake-plugin", lambda s: s.state == "running" and s.pid != first.pid)

        states = {s.state for s in seen}
        assert states & {"crashed", "starting"}  # the gap was reported honestly
        assert runtime.spawn_count == 2
        recovery = seen[-1]
        assert recovery.pid is not None and recovery.pid != first.pid
        assert any("scheduling auto-restart 1/3" in r.getMessage() for r in caplog.records)
        assert any("exit code 7" in r.getMessage() for r in caplog.records)
    finally:
        runtime.stop("fake-plugin")


# ---------------------------------------------------------------------------
# T2: budget exhaustion -> honest terminal crashed, no restart loop
# ---------------------------------------------------------------------------


def test_budget_exhausted_stays_crashed_with_count_and_reason(tmp_path: Path):
    crash_file = tmp_path / "crash"
    # Every instance crashes ~0.35s after READY: initial + 3 bounded restarts.
    runtime, manifest, package_root, data_root = _make_runtime(
        tmp_path,
        crash_file=crash_file,
        exit_after_seconds=0.35,
        exit_code=9,
    )
    try:
        runtime.start(manifest, package_root, data_root)
        seen = _wait_for(
            runtime,
            "fake-plugin",
            lambda s: s.state == "crashed" and "budget exhausted" in s.reason,
            timeout=20.0,
        )
        snap = seen[-1]
        assert snap.crash_count == 3
        assert "exit code 9" in snap.reason
        assert "manual restart required" in snap.reason
        assert runtime.spawn_count == 4  # initial + exactly 3 restarts

        # No fifth spawn: the loop is bounded, not silent.
        time.sleep(1.5)
        assert runtime.spawn_count == 4
        assert runtime.status("fake-plugin").state == "crashed"

        # Manual restart is the documented escape hatch and resets the budget.
        restarted = runtime.start(manifest, package_root, data_root)
        assert restarted.state == "running"
        assert runtime.spawn_count == 5
        assert "fake-plugin" not in runtime._crash_ledgers
    finally:
        runtime.stop("fake-plugin")


# ---------------------------------------------------------------------------
# T3: stable running resets the budget
# ---------------------------------------------------------------------------


def test_stable_running_resets_budget(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG, logger="mikazuki.plugin_host.runtime")
    crash_file = tmp_path / "crash"
    runtime, manifest, package_root, data_root = _make_runtime(
        tmp_path,
        crash_file=crash_file,
        crash_stable_reset_seconds=1.0,
    )
    try:
        runtime.start(manifest, package_root, data_root)
        first_pid = runtime.status("fake-plugin").pid

        _trigger_crash(crash_file)
        _wait_for(runtime, "fake-plugin", lambda s: s.state == "running" and s.pid != first_pid)
        assert runtime.spawn_count == 2
        assert any("scheduling auto-restart 1/3" in r.getMessage() for r in caplog.records)

        # Stable for > crash_stable_reset_seconds -> budget reset.
        time.sleep(1.4)
        assert any("budget reset" in r.getMessage() for r in caplog.records)
        assert "fake-plugin" not in runtime._crash_ledgers
        second_pid = runtime.status("fake-plugin").pid

        # A second, later crash is again a FRESH budget (restart 1, not 2).
        _trigger_crash(crash_file)
        _wait_for(runtime, "fake-plugin", lambda s: s.state == "running" and s.pid != second_pid, timeout=15.0)
        assert runtime.spawn_count == 3
        restart_lines = [r.getMessage() for r in caplog.records if "scheduling auto-restart 1/3" in r.getMessage()]
        assert len(restart_lines) == 2
    finally:
        runtime.stop("fake-plugin")


# ---------------------------------------------------------------------------
# T4: user stop suppresses a pending auto-restart
# ---------------------------------------------------------------------------


def test_stop_suppresses_pending_restart(tmp_path: Path):
    crash_file = tmp_path / "crash"
    runtime, manifest, package_root, data_root = _make_runtime(
        tmp_path,
        crash_file=crash_file,
        crash_backoff_seconds=(3.0, 3.0, 3.0),  # long backoff: the restart is pending for a while
    )
    try:
        runtime.start(manifest, package_root, data_root)
        _trigger_crash(crash_file)
        # Crash detected, restart scheduled but not yet due.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and "fake-plugin" not in runtime._pending_restarts:
            time.sleep(0.02)
        assert "fake-plugin" in runtime._pending_restarts

        runtime.stop("fake-plugin")
        time.sleep(3.5)  # well past the 3s backoff
        assert runtime.spawn_count == 1  # the pending restart was abandoned
        assert runtime.status("fake-plugin").state == "stopped"
    finally:
        runtime.stop("fake-plugin")


# ---------------------------------------------------------------------------
# T5: manual restart does not consume the crash budget
# ---------------------------------------------------------------------------


def test_manual_restart_resets_budget_and_does_not_count(tmp_path: Path):
    crash_file = tmp_path / "crash"
    runtime, manifest, package_root, data_root = _make_runtime(
        tmp_path,
        crash_file=crash_file,
        exit_after_seconds=0.35,
        exit_code=9,
    )
    try:
        runtime.start(manifest, package_root, data_root)
        first_pid = runtime.status("fake-plugin").pid
        # Let it crash and auto-restart once (budget now at 1/3).
        _wait_for(runtime, "fake-plugin", lambda s: s.state == "running" and s.pid != first_pid, timeout=15.0)
        runtime.stop("fake-plugin")
        assert runtime.spawn_count >= 2
        # Manual restart = fresh lifecycle: the ledger must be empty.
        runtime.start(manifest, package_root, data_root)
        assert "fake-plugin" not in runtime._crash_ledgers
        manual_pid = runtime.status("fake-plugin").pid
        # It crashes again; the auto-restart is a FRESH budget (attempt 1, not
        # 2) and recovers instead of going terminal.
        _wait_for(runtime, "fake-plugin", lambda s: s.state == "running" and s.pid != manual_pid, timeout=15.0)
    finally:
        runtime.stop("fake-plugin")


# ---------------------------------------------------------------------------
# T6: supervision disabled -> legacy behavior (no auto-restart)
# ---------------------------------------------------------------------------


def test_supervision_disabled_keeps_legacy_behavior(tmp_path: Path):
    crash_file = tmp_path / "crash"
    runtime, manifest, package_root, data_root = _make_runtime(
        tmp_path,
        crash_file=crash_file,
        crash_supervision=False,
    )
    try:
        runtime.start(manifest, package_root, data_root)
        _trigger_crash(crash_file)
        # Legacy: first status after the crash reports crashed and tears down.
        deadline = time.monotonic() + 5.0
        last = None
        while time.monotonic() < deadline:
            last = runtime.status("fake-plugin")
            if last.state == "crashed":
                break
            time.sleep(0.05)
        assert last is not None and last.state == "crashed"
        assert runtime.status("fake-plugin").state == "stopped"
        time.sleep(1.0)
        assert runtime.spawn_count == 1  # never restarted
    finally:
        runtime.stop("fake-plugin")


# ---------------------------------------------------------------------------
# T7: a live-but-unhealthy process is NOT auto-restarted (scope: process exit)
# ---------------------------------------------------------------------------


def test_unhealthy_live_process_is_not_auto_restarted(tmp_path: Path):
    crash_file = tmp_path / "crash"
    runtime, manifest, package_root, data_root = _make_runtime(
        tmp_path,
        crash_file=crash_file,
        unhealthy_after_seconds=0.5,
    )
    try:
        runtime.start(manifest, package_root, data_root)
        assert runtime.spawn_count == 1
        deadline = time.monotonic() + 6.0
        last = None
        while time.monotonic() < deadline:
            last = runtime.status("fake-plugin")
            if last.state == "crashed" and "health check failed" in last.reason:
                break
            time.sleep(0.1)
        assert last is not None and last.state == "crashed"
        time.sleep(1.0)
        assert runtime.spawn_count == 1  # health failure is out of the restart scope
    finally:
        runtime.stop("fake-plugin")

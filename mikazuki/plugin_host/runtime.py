from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import secrets
import subprocess
import threading
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit


logger = logging.getLogger("mikazuki.plugin_host.runtime")

RuntimeState = Literal["stopped", "starting", "running", "crashed"]


@dataclass(frozen=True)
class RuntimeSnapshot:
    state: RuntimeState
    version: str | None = None
    pid: int | None = None
    protocol_version: str | None = None
    reason: str = ""
    ui_url: str | None = None
    # P1-1: auto-restarts already spent from the crash budget (0 = none).
    crash_count: int = 0


class RuntimeManifest(Protocol):
    id: str
    version: str
    protocol_version: str

    @property
    def runtime(self): ...


class PluginRuntimeController(Protocol):
    def start(self, manifest: RuntimeManifest, package_root: Path, data_root: Path) -> RuntimeSnapshot: ...

    def stop(self, plugin_id: str) -> None: ...

    def status(self, plugin_id: str) -> RuntimeSnapshot: ...

    async def request(self, plugin_id: str, request_id: str, method: str, params: dict[str, Any]) -> Any: ...

    async def stream(
        self,
        plugin_id: str,
        request_id: str,
        method: str,
        params: dict[str, Any],
    ) -> AsyncIterator[Any]: ...

    def verify_host_tool_token(self, plugin_id: str, supplied_token: str) -> bool: ...


@dataclass
class _ProcessHandle:
    process: subprocess.Popen[str]
    version: str
    protocol_version: str
    port: int
    token: str = field(repr=False)
    host_tool_token: str = field(repr=False)
    ui_url: str | None = None
    child_pid: int | None = None
    # P1-1: launch context kept on the handle so the crash supervisor can
    # restart the plugin without any other component holding the manifest.
    manifest: Any = None
    package_root: Path | None = None
    data_root: Path | None = None


@dataclass
class _CrashLedger:
    """P1-1 bounded auto-restart bookkeeping for one plugin.

    ``restart_times`` holds the monotonic timestamps of every auto-restart
    SCHEDULED inside the rolling window (budget = at most
    ``crash_budget_max`` entries). The ledger is reset when the plugin has
    stayed up for ``crash_stable_reset_seconds`` after its last crash, or
    whenever the plugin is stopped by a user action (a fresh enable/restart
    is a fresh lifecycle; manual restarts never count against the budget).
    """

    version: str
    restart_times: deque[float] = field(default_factory=deque)
    last_crash_at: float | None = None
    last_exit: int | None = None
    last_reason: str = ""
    terminal: bool = False
    terminal_summary: str = ""


@dataclass
class _PendingRestart:
    """A scheduled (backed-off) auto-restart awaiting its deadline."""

    plugin_id: str
    manifest: Any
    package_root: Path
    data_root: Path
    run_at: float
    attempt: int


def _is_loopback_ui_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.hostname == "127.0.0.1"
        and parsed.port is not None
        and not parsed.username
        and not parsed.password
    )


class ExecutablePluginRuntime:
    """Supervise manifest-declared loopback sidecars without plugin-specific imports."""

    def __init__(
        self,
        *,
        parent_pid: int | None = None,
        startup_timeout: float = 120.0,
        ui_ready_timeout: float = 120.0,
        host_tool_base_url: str | None = None,
        crash_supervision: bool = True,
        crash_backoff_seconds: tuple[float, ...] = (2.0, 5.0, 15.0),
        crash_budget_max: int = 3,
        crash_window_seconds: float = 600.0,
        crash_stable_reset_seconds: float = 300.0,
        supervisor_poll_seconds: float = 1.0,
    ) -> None:
        self._parent_pid = parent_pid or os.getpid()
        self._startup_timeout = startup_timeout
        self._ui_ready_timeout = ui_ready_timeout
        if host_tool_base_url is not None:
            parsed = urlsplit(host_tool_base_url)
            if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
                raise ValueError("host Tool base URL must use an explicit 127.0.0.1 port")
        self._host_tool_base_url = host_tool_base_url
        self._guard = threading.RLock()
        self._handles: dict[str, _ProcessHandle] = {}
        # P1-1: crash-bounded auto-restart. A single supervisor thread polls
        # every handle; an unexpected child exit (while the plugin is still
        # supposed to run) is restarted with a bounded budget instead of
        # staying crashed until a human intervenes.
        self._crash_supervision = crash_supervision
        self._crash_backoff_seconds = tuple(crash_backoff_seconds) or (2.0,)
        self._crash_budget_max = max(0, crash_budget_max)
        self._crash_window_seconds = crash_window_seconds
        self._crash_stable_reset_seconds = crash_stable_reset_seconds
        self._supervisor_poll_seconds = max(0.05, supervisor_poll_seconds)
        self._crash_ledgers: dict[str, _CrashLedger] = {}
        self._pending_restarts: dict[str, _PendingRestart] = {}
        if self._crash_supervision:
            self._supervisor_stop = threading.Event()
            threading.Thread(target=self._supervisor_loop, daemon=True, name="plugin-runtime-supervisor").start()

    def start(self, manifest: RuntimeManifest, package_root: Path, data_root: Path) -> RuntimeSnapshot:
        # Public (user-initiated) start: a fresh lifecycle, so any prior crash
        # bookkeeping for this plugin is cleared (manual restarts never count
        # against the auto-restart budget).
        with self._guard:
            self._stop_internal(manifest.id, reset_crash_state=True)
            return self._launch_locked(manifest, package_root, data_root)

    def _launch_locked(self, manifest: RuntimeManifest, package_root: Path, data_root: Path) -> RuntimeSnapshot:
        with self._guard:
            executable = (package_root / manifest.runtime.entrypoint).resolve()
            try:
                executable.relative_to(package_root.resolve())
            except ValueError as exc:
                raise RuntimeError("plugin runtime entrypoint escapes its package") from exc
            if not executable.is_file():
                raise RuntimeError("plugin runtime entrypoint is missing")

            data_root.mkdir(parents=True, exist_ok=True)
            sidecar_token = secrets.token_urlsafe(32)
            host_tool_token = secrets.token_urlsafe(32)
            child_env = self._child_environment()
            child_env.update(
                {
                    "NEXT_TRAINER_SIDECAR_PORT": "0",
                    "NEXT_TRAINER_SIDECAR_TOKEN": sidecar_token,
                    "NEXT_TRAINER_HOST_TOOL_TOKEN": host_tool_token,
                    "NEXT_TRAINER_PLUGIN_DATA_ROOT": str(data_root.resolve()),
                    "NEXT_TRAINER_PROJECT_ROOT": str(Path.cwd().resolve()),
                    "NEXT_TRAINER_PARENT_PID": str(self._parent_pid),
                }
            )
            if self._host_tool_base_url is not None:
                child_env["NEXT_TRAINER_HOST_TOOL_BASE_URL"] = self._host_tool_base_url
            process = self._spawn_process(executable, data_root, child_env)
            try:
                ready = self._wait_ready(process)
                if ready.get("host") != "127.0.0.1":
                    raise RuntimeError("plugin runtime READY host is not loopback")
                if str(ready.get("protocolVersion")) != manifest.protocol_version:
                    raise RuntimeError("plugin runtime protocol does not match manifest")
                port = ready.get("port")
                if not isinstance(port, int) or not 0 < port <= 65535:
                    raise RuntimeError("plugin runtime READY port is invalid")
                ui_url = ready.get("uiUrl")
                if ui_url is not None and (not isinstance(ui_url, str) or not _is_loopback_ui_url(ui_url)):
                    raise RuntimeError("plugin runtime READY uiUrl is not a loopback URL")
                child_pid = ready.get("childPid")
                if child_pid is not None and (not isinstance(child_pid, int) or isinstance(child_pid, bool) or child_pid <= 0):
                    raise RuntimeError("plugin runtime READY childPid is invalid")
                handle = _ProcessHandle(
                    process=process,
                    version=manifest.version,
                    protocol_version=manifest.protocol_version,
                    port=port,
                    token=sidecar_token,
                    host_tool_token=host_tool_token,
                    ui_url=ui_url if isinstance(ui_url, str) else None,
                    child_pid=child_pid if isinstance(child_pid, int) else None,
                    manifest=manifest,
                    package_root=package_root,
                    data_root=data_root,
                )
                self._handles[manifest.id] = handle
                snapshot = self._probe(handle)
                if snapshot.state != "running":
                    raise RuntimeError(snapshot.reason or "plugin runtime health check failed")
                # V30 UX gate: the launcher's own readiness wait only proves the
                # UI port answers ANY http status; the first real page render
                # (what the floating panel loads) can lag behind. Block the
                # enable/restart operation until the UI actually serves a
                # non-empty document, so the user never opens a blank panel.
                # Timeout raises into the same except path below: the runtime
                # is torn down and enable reports the failure honestly.
                if handle.ui_url is not None:
                    self._wait_ui_ready(handle)
                return snapshot
            except Exception:
                self._terminate(process)
                self._handles.pop(manifest.id, None)
                raise

    def _spawn_process(self, executable: Path, data_root: Path, child_env: dict[str, str]) -> subprocess.Popen[str]:
        """Single seam where the sidecar is spawned (P1-1 tests override this)."""
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        return subprocess.Popen(
            [str(executable)],
            cwd=str(data_root.resolve()),
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
        )

    @staticmethod
    def _child_environment() -> dict[str, str]:
        allowed = {
            "SystemRoot",
            "WINDIR",
            "COMSPEC",
            "PATHEXT",
            "TEMP",
            "TMP",
            "LANG",
            "LC_ALL",
            "SSL_CERT_FILE",
            "NODE_EXTRA_CA_CERTS",
        }
        environment = {key: value for key, value in os.environ.items() if key in allowed}
        # Deliberately NOT forwarding HTTP(S)_PROXY here: the host refuses to
        # launder arbitrary host-environment variables (a proxy URL can embed
        # credentials) into a plugin child that runs with a different trust
        # level. Plugins that need egress configure it in their OWN scoped
        # config — for the bundled npm runtime that is the editable
        # `<agentDir>/npmrc` (proxy/https-proxy/registry), which npm honors
        # regardless of the stripped environment. See the plugin's
        # npm-runtime bootstrap for that config's generation.
        # Keep the sidecar launch environment deterministic while retaining the
        # system loader path required by a compiled Windows executable.  Never
        # inherit the host's PATH: it may expose project tooling or credentials.
        if os.name == "nt":
            system_root = environment.get("SystemRoot") or environment.get("WINDIR") or r"C:\Windows"
            environment["SystemRoot"] = system_root
            environment["WINDIR"] = system_root
            environment["PATH"] = f"{system_root}\\System32;{system_root}"
        # Verifier-only escape hatch: the Host process must explicitly opt in
        # to HTTP loopback provider endpoints (integration verifiers that use
        # a fake local Provider).  Production hosts never set this variable,
        # so the deployed sidecar stays HTTPS-only.
        if os.environ.get("NEXT_TRAINER_ALLOW_HTTP_LOOPBACK") == "1":
            environment["NEXT_TRAINER_ALLOW_HTTP_LOOPBACK"] = "1"
        return environment

    def stop(self, plugin_id: str) -> None:
        # User-facing stop: fresh lifecycle, crash bookkeeping cleared.
        with self._guard:
            self._stop_internal(plugin_id, reset_crash_state=True)

    def _stop_internal(self, plugin_id: str, *, reset_crash_state: bool) -> None:
        handle = self._handles.pop(plugin_id, None)
        self._pending_restarts.pop(plugin_id, None)
        if reset_crash_state:
            self._crash_ledgers.pop(plugin_id, None)
        if handle is not None:
            self._terminate(handle.process)
            self._kill_child_tree(handle)

    def status(self, plugin_id: str) -> RuntimeSnapshot:
        with self._guard:
            handle = self._handles.get(plugin_id)
            pending = self._pending_restarts.get(plugin_id)
            ledger = self._crash_ledgers.get(plugin_id)
            supervision = self._crash_supervision
        if handle is not None:
            snapshot = self._probe(handle)
            if snapshot.state == "crashed" and not supervision:
                # Legacy behavior (supervision disabled): the first crashed
                # status tears the handle down.
                self._handles.pop(plugin_id, None)
                self._terminate(handle.process)
                return snapshot
            if snapshot.state == "crashed":
                # P1-1: under supervision the supervisor OWNS dead processes
                # (bounded restart within one poll interval) and a
                # live-but-unhealthy process stays visible as crashed for a
                # manual restart. status() must NEVER tear down here — doing
                # so from a racy status() call (e.g. a momentary health-check
                # timeout on a still-live process) would destroy the crash
                # bookkeeping and silently kill self-healing.
                return RuntimeSnapshot(
                    state="crashed",
                    version=handle.version,
                    pid=handle.process.pid,
                    protocol_version=handle.protocol_version,
                    reason=snapshot.reason,
                    crash_count=len(ledger.restart_times) if ledger is not None else 0,
                )
            return snapshot
        if pending is not None:
            return RuntimeSnapshot(
                state="starting",
                version=ledger.version if ledger is not None else None,
                reason=f"auto-restart in progress (attempt {pending.attempt})",
                crash_count=len(ledger.restart_times) if ledger is not None else 0,
            )
        if ledger is not None and ledger.terminal:
            return RuntimeSnapshot(
                state="crashed",
                version=ledger.version,
                reason=ledger.terminal_summary,
                crash_count=len(ledger.restart_times),
            )
        return RuntimeSnapshot(state="stopped")

    # ------------------------------------------------------------------
    # P1-1: crash-bounded auto-restart supervisor
    # ------------------------------------------------------------------

    def _supervisor_loop(self) -> None:
        while not self._supervisor_stop.wait(self._supervisor_poll_seconds):
            try:
                self._supervisor_tick()
            except Exception:
                # The supervisor must never die silently: a dead supervisor
                # would silently disable self-healing while the UI still
                # shows "enabled". Log and keep polling.
                logger.exception("plugin runtime supervisor tick failed")

    def _supervisor_tick(self) -> None:
        now = time.monotonic()
        due: list[_PendingRestart] = []
        with self._guard:
            # 1) Budget reset: stable running after a crash.
            for plugin_id, ledger in list(self._crash_ledgers.items()):
                if ledger.terminal or ledger.last_crash_at is None:
                    continue
                if now - ledger.last_crash_at < self._crash_stable_reset_seconds:
                    continue
                handle = self._handles.get(plugin_id)
                if handle is not None and handle.process.poll() is None:
                    self._crash_ledgers.pop(plugin_id, None)
                    logger.info(
                        "plugin %s stable for %.0fs after crash; auto-restart budget reset",
                        plugin_id,
                        self._crash_stable_reset_seconds,
                    )
            # 2) Unexpected child exits while the plugin is still registered.
            for plugin_id, handle in list(self._handles.items()):
                ledger = self._crash_ledgers.get(plugin_id)
                if ledger is not None and ledger.terminal:
                    continue
                exit_code = handle.process.poll()
                if exit_code is None:
                    continue
                self._schedule_crash_response(plugin_id, handle, exit_code, now)
            # 3) Backed-off restarts whose deadline has arrived.
            due = [entry for entry in self._pending_restarts.values() if now >= entry.run_at]
        for entry in due:
            self._run_pending_restart(entry)

    def _schedule_crash_response(self, plugin_id: str, handle: _ProcessHandle, exit_code: int, now: float) -> None:
        """Record the crash and schedule the bounded restart (or terminal).

        Called with the guard held. The dead handle is removed here so
        ``status()`` and the manager never act on it a second time.
        """
        ledger = self._crash_ledgers.get(plugin_id)
        if ledger is None or ledger.version != handle.version:
            ledger = _CrashLedger(version=handle.version)
        cutoff = now - self._crash_window_seconds
        while ledger.restart_times and ledger.restart_times[0] <= cutoff:
            ledger.restart_times.popleft()
        ledger.last_crash_at = now
        ledger.last_exit = exit_code
        self._crash_ledgers[plugin_id] = ledger

        self._handles.pop(plugin_id, None)
        self._pending_restarts.pop(plugin_id, None)
        self._terminate(handle.process)
        self._kill_child_tree(handle)

        if len(ledger.restart_times) >= self._crash_budget_max:
            summary = (
                f"plugin runtime process exited (exit code {exit_code}); "
                f"{len(ledger.restart_times)} auto-restart(s) already used in the last "
                f"{self._crash_window_seconds / 60:.0f} minutes - auto-restart budget "
                f"exhausted, manual restart required"
            )
            ledger.terminal = True
            ledger.terminal_summary = summary
            ledger.last_reason = summary
            logger.error("plugin %s %s", plugin_id, summary)
            return

        if handle.manifest is None or handle.package_root is None or handle.data_root is None:
            summary = "plugin runtime auto-restart impossible (launch context unknown)"
            ledger.terminal = True
            ledger.terminal_summary = summary
            ledger.last_reason = summary
            logger.error("plugin %s %s", plugin_id, summary)
            return

        attempt = len(ledger.restart_times) + 1
        backoff = self._crash_backoff_seconds[min(attempt - 1, len(self._crash_backoff_seconds) - 1)]
        ledger.restart_times.append(now)
        ledger.last_reason = f"plugin runtime process exited (exit code {exit_code})"
        self._pending_restarts[plugin_id] = _PendingRestart(
            plugin_id=plugin_id,
            manifest=handle.manifest,
            package_root=handle.package_root,
            data_root=handle.data_root,
            run_at=now + backoff,
            attempt=attempt,
        )
        logger.warning(
            "plugin %s child process exited (exit code %s); scheduling auto-restart %d/%d in %.1fs",
            plugin_id,
            exit_code,
            attempt,
            self._crash_budget_max,
            backoff,
        )

    def _launch_supervised(self, entry: _PendingRestart) -> RuntimeSnapshot | None:
        """Restart worker for one scheduled auto-restart (own thread).

        Returns None when a user action (stop/start) intervened.
        """
        with self._guard:
            if self._pending_restarts.get(entry.plugin_id) is not entry:
                return None
            # Supervised relaunch is a CONTINUATION of the crash loop: the
            # ledger must survive, so only the process is torn down.
            self._stop_internal(entry.plugin_id, reset_crash_state=False)
            return self._launch_locked(entry.manifest, entry.package_root, entry.data_root)

    def _run_pending_restart(self, entry: _PendingRestart) -> None:
        logger.info("plugin %s auto-restart attempt %d starting", entry.plugin_id, entry.attempt)
        try:
            snapshot = self._launch_supervised(entry)
        except Exception as exc:
            self._record_restart_failure(entry, str(exc))
            return
        if snapshot is None:
            return  # user stop/start intervened; the user action owns the lifecycle
        with self._guard:
            ledger = self._crash_ledgers.get(entry.plugin_id)
        if ledger is not None:
            logger.info("plugin %s auto-restart attempt %d recovered (pid %s)", entry.plugin_id, entry.attempt, snapshot.pid)

    def _record_restart_failure(self, entry: _PendingRestart, reason: str) -> None:
        """A failed relaunch consumes budget like any crash (no silent loops)."""
        logger.error("plugin %s auto-restart attempt %d failed: %s", entry.plugin_id, entry.attempt, reason)
        now = time.monotonic()
        with self._guard:
            ledger = self._crash_ledgers.get(entry.plugin_id)
            if ledger is None:
                return  # user stop intervened
            ledger.last_reason = reason
            if len(ledger.restart_times) >= self._crash_budget_max:
                summary = (
                    f"plugin runtime auto-restart failed {len(ledger.restart_times)} time(s) in the last "
                    f"{self._crash_window_seconds / 60:.0f} minutes ({reason}) - auto-restart budget "
                    f"exhausted, manual restart required"
                )
                ledger.terminal = True
                ledger.terminal_summary = summary
                logger.error("plugin %s %s", entry.plugin_id, summary)
                return
            attempt = len(ledger.restart_times) + 1
            backoff = self._crash_backoff_seconds[min(attempt - 1, len(self._crash_backoff_seconds) - 1)]
            ledger.restart_times.append(now)
            self._pending_restarts[entry.plugin_id] = _PendingRestart(
                plugin_id=entry.plugin_id,
                manifest=entry.manifest,
                package_root=entry.package_root,
                data_root=entry.data_root,
                run_at=now + backoff,
                attempt=attempt,
            )

    async def request(self, plugin_id: str, request_id: str, method: str, params: dict[str, Any]) -> Any:
        handle = self._running_handle(plugin_id)
        return await asyncio.to_thread(
            self._post_json,
            handle,
            "/bridge/requests",
            {"requestId": request_id, "method": method, "params": params},
            request_id,
        )

    async def stream(
        self,
        plugin_id: str,
        request_id: str,
        method: str,
        params: dict[str, Any],
    ) -> AsyncIterator[Any]:
        handle = self._running_handle(plugin_id)
        payload = {"requestId": request_id, "method": method, "params": params}
        return self._event_stream(handle, payload, request_id)

    def verify_host_tool_token(self, plugin_id: str, supplied_token: str) -> bool:
        with self._guard:
            handle = self._handles.get(plugin_id)
            return bool(
                handle is not None
                and supplied_token
                and secrets.compare_digest(supplied_token, handle.host_tool_token)
            )

    def _running_handle(self, plugin_id: str) -> _ProcessHandle:
        with self._guard:
            handle = self._handles.get(plugin_id)
            if handle is None or handle.process.poll() is not None:
                raise RuntimeError("plugin runtime is not running")
            return handle

    def _wait_ready(self, process: subprocess.Popen[str]) -> dict:
        if process.stdout is None:
            raise RuntimeError("plugin runtime stdout is unavailable")
        lines: queue.Queue[str | None] = queue.Queue(maxsize=256)
        ready_done = threading.Event()

        def read_lines() -> None:
            try:
                for line in process.stdout:
                    if ready_done.is_set():
                        continue
                    try:
                        lines.put(line, timeout=0.1)
                    except queue.Full:
                        continue
            finally:
                if not ready_done.is_set():
                    try:
                        lines.put_nowait(None)
                    except queue.Full:
                        pass

        threading.Thread(target=read_lines, daemon=True).start()
        deadline = time.monotonic() + self._startup_timeout
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None and lines.empty():
                    break
                try:
                    line = lines.get(timeout=min(0.1, max(0.01, deadline - time.monotonic())))
                except queue.Empty:
                    continue
                if line is None:
                    break
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict) and value.get("type") == "READY":
                    return value
            raise RuntimeError("plugin runtime did not become ready")
        finally:
            ready_done.set()

    @staticmethod
    def _request(handle: _ProcessHandle, path: str, payload: dict[str, Any], request_id: str) -> urllib.request.Request:
        return urllib.request.Request(
            f"http://127.0.0.1:{handle.port}{path}",
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {handle.token}",
                "Content-Type": "application/json",
                "X-Request-Id": request_id,
            },
            method="POST",
        )

    @classmethod
    def _post_json(
        cls,
        handle: _ProcessHandle,
        path: str,
        payload: dict[str, Any],
        request_id: str,
    ) -> Any:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(cls._request(handle, path, payload, request_id), timeout=30.0) as response:
                value = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("plugin runtime request failed") from exc
        if (
            not isinstance(value, dict)
            or value.get("ok") is not True
            or value.get("requestId") != request_id
            or "data" not in value
        ):
            raise RuntimeError("plugin runtime returned an invalid response")
        return value["data"]

    @classmethod
    def _event_stream(
        cls,
        handle: _ProcessHandle,
        payload: dict[str, Any],
        request_id: str,
    ) -> AsyncIterator[Any]:
        async def iterate() -> AsyncIterator[Any]:
            loop = asyncio.get_running_loop()
            events: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
            cancelled = threading.Event()
            response_box: list[Any] = []

            def publish(kind: str, value: Any) -> None:
                loop.call_soon_threadsafe(events.put_nowait, (kind, value))

            def read_stream() -> None:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                try:
                    response = opener.open(cls._request(handle, "/bridge/streams", payload, request_id), timeout=30.0)
                    response_box.append(response)
                    if response.headers.get_content_type() != "text/event-stream":
                        raise RuntimeError("plugin runtime stream response is invalid")
                    # Keep the established local SSE connection alive according to
                    # the plugin runtime's own session policy, not a Host read timeout.
                    socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                    if socket is not None:
                        socket.settimeout(None)
                    data_lines: list[str] = []
                    def publish_data() -> None:
                        if not data_lines:
                            return
                        value = json.loads("\n".join(data_lines))
                        data_lines.clear()
                        if not isinstance(value, dict) or value.get("requestId") != request_id:
                            raise RuntimeError("plugin runtime stream envelope is invalid")
                        if value.get("ok") is not True or "data" not in value:
                            raise RuntimeError("plugin runtime stream reported failure")
                        publish("data", value["data"])

                    for raw_line in response:
                        if cancelled.is_set():
                            break
                        line = raw_line.decode("utf-8", errors="strict").rstrip("\r\n")
                        if line == "":
                            publish_data()
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())
                    publish_data()
                except Exception:
                    if not cancelled.is_set():
                        publish("error", None)
                finally:
                    if response_box:
                        response_box[0].close()
                    publish("done", None)

            threading.Thread(target=read_stream, daemon=True).start()
            try:
                while True:
                    kind, value = await events.get()
                    if kind == "data":
                        yield value
                    elif kind == "error":
                        raise RuntimeError("plugin runtime event stream failed")
                    else:
                        break
            finally:
                cancelled.set()
                if response_box:
                    response_box[0].close()

        return iterate()

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    @staticmethod
    def _kill_child_tree(handle: _ProcessHandle) -> None:
        """Best-effort removal of a runtime's grandchild tree.

        Windows TerminateProcess cannot be intercepted by the sidecar, so a
        runtime that spawns its own server tree (e.g. pi-web) reports the
        server PID in READY; the host removes the tree directly.  The
        sidecar's own parent-liveness monitor covers the host-crash case.
        """
        child_pid = handle.child_pid
        if child_pid is None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(child_pid)],
                    capture_output=True,
                    timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:
                return
        else:
            import signal

            # The launcher (POSIX) spawns its server in its own process group,
            # so killing the group mirrors taskkill /F /T on Windows and also
            # removes agent-spawned tool processes. Fall back to the single
            # process when the pid is not a group leader (e.g. older launchers).
            try:
                os.killpg(child_pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                return
            except OSError:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except OSError:
                    return

    def _wait_ui_ready(
        self,
        handle: _ProcessHandle,
        *,
        poll_interval: float = 0.5,
        read_cap_bytes: int = 64 * 1024,
        attempt_timeout: float = 10.0,
    ) -> None:
        """Block until the plugin UI serves a real, non-empty document.

        Ready means a completed HTTP response with a 2xx/3xx status AND a
        non-empty body on the UI origin (query stripped: the panel's ``?cwd=``
        parameter is irrelevant to boot). Connection errors, idle timeouts and
        empty responses are retried until ``self._ui_ready_timeout`` expires,
        at which point a RuntimeError tears the runtime down via start()'s
        except path.
        """
        parsed = urlsplit(handle.ui_url or "")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        target = origin + (parsed.path or "/")
        deadline = time.monotonic() + self._ui_ready_timeout
        last_error = "no response"
        while True:
            try:
                request = urllib.request.Request(target, headers={"Accept": "text/html"})
                with urllib.request.urlopen(request, timeout=attempt_timeout) as response:
                    body = response.read(read_cap_bytes)
                    if 200 <= response.status < 400 and body:
                        return
                    last_error = f"HTTP {response.status} with empty body" if response.status < 400 else f"HTTP {response.status}"
            except Exception as exc:  # noqa: BLE001 — any network error means "not ready yet"
                last_error = str(exc) or exc.__class__.__name__
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"plugin UI did not become ready within {self._ui_ready_timeout:.0f}s ({last_error})"
                ) from None
            time.sleep(poll_interval)

    @staticmethod
    def _probe(handle: _ProcessHandle) -> RuntimeSnapshot:
        if handle.process.poll() is not None:
            return RuntimeSnapshot(
                state="crashed",
                version=handle.version,
                pid=handle.process.pid,
                protocol_version=handle.protocol_version,
                reason="plugin runtime process exited",
            )
        request = urllib.request.Request(
            f"http://127.0.0.1:{handle.port}/health",
            headers={"Authorization": f"Bearer {handle.token}", "X-Request-Id": secrets.token_hex(16)},
        )
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            data = payload.get("data") if isinstance(payload, dict) else None
            if (
                not payload.get("ok")
                or not isinstance(data, dict)
                or data.get("status") != "ok"
                or str(data.get("protocolVersion")) != handle.protocol_version
            ):
                raise ValueError("invalid health response")
        except Exception:
            return RuntimeSnapshot(
                state="crashed",
                version=handle.version,
                pid=handle.process.pid,
                protocol_version=handle.protocol_version,
                reason="plugin runtime health check failed",
            )
        return RuntimeSnapshot(
            state="running",
            version=handle.version,
            pid=handle.process.pid,
            protocol_version=handle.protocol_version,
            ui_url=handle.ui_url,
        )


__all__ = ["ExecutablePluginRuntime", "PluginRuntimeController", "RuntimeSnapshot"]

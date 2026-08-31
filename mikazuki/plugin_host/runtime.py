from __future__ import annotations

import asyncio
import json
import os
import queue
import secrets
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit


RuntimeState = Literal["stopped", "starting", "running", "crashed"]


@dataclass(frozen=True)
class RuntimeSnapshot:
    state: RuntimeState
    version: str | None = None
    pid: int | None = None
    protocol_version: str | None = None
    reason: str = ""
    ui_url: str | None = None


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
        host_tool_base_url: str | None = None,
    ) -> None:
        self._parent_pid = parent_pid or os.getpid()
        self._startup_timeout = startup_timeout
        if host_tool_base_url is not None:
            parsed = urlsplit(host_tool_base_url)
            if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
                raise ValueError("host Tool base URL must use an explicit 127.0.0.1 port")
        self._host_tool_base_url = host_tool_base_url
        self._guard = threading.RLock()
        self._handles: dict[str, _ProcessHandle] = {}

    def start(self, manifest: RuntimeManifest, package_root: Path, data_root: Path) -> RuntimeSnapshot:
        with self._guard:
            self.stop(manifest.id)
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
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(
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
                )
                self._handles[manifest.id] = handle
                snapshot = self._probe(handle)
                if snapshot.state != "running":
                    raise RuntimeError(snapshot.reason or "plugin runtime health check failed")
                return snapshot
            except Exception:
                self._terminate(process)
                self._handles.pop(manifest.id, None)
                raise

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
        with self._guard:
            handle = self._handles.pop(plugin_id, None)
            if handle is not None:
                self._terminate(handle.process)
                self._kill_child_tree(handle)

    def status(self, plugin_id: str) -> RuntimeSnapshot:
        with self._guard:
            handle = self._handles.get(plugin_id)
            if handle is None:
                return RuntimeSnapshot(state="stopped")
            snapshot = self._probe(handle)
            if snapshot.state == "crashed":
                self._handles.pop(plugin_id, None)
                self._terminate(handle.process)
            return snapshot

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

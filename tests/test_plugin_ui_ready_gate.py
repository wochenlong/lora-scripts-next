"""V30 UI-ready gate: enable/restart must not report success until the plugin
UI (pi-web) actually serves a rendered, non-empty document — not merely until
the UI port answers any HTTP status (the launcher's own readiness wait only
proves that). Users previously opened the floating panel into a blank page
while pi-web finished its first render.

These unit tests drive ``ExecutablePluginRuntime._wait_ui_ready`` against
local loopback HTTP servers (same pattern as the acquisition tests).
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from mikazuki.plugin_host.runtime import ExecutablePluginRuntime, _ProcessHandle

HTML = b"<!doctype html><html><head><title>pi-web</title></head><body><div id=\"root\"></div></body></html>"


class _StubProcess:
    """_wait_ui_ready only reads handle.ui_url; the process is never touched."""

    def poll(self):  # pragma: no cover - not exercised by the gate
        return None


def _handle(ui_url: str) -> _ProcessHandle:
    return _ProcessHandle(
        process=_StubProcess(),  # type: ignore[arg-type]
        version="0.0.0",
        protocol_version="1",
        port=urlsplit(ui_url).port,  # type: ignore[arg-type]
        token="t" * 40,
        host_tool_token="h" * 40,
        ui_url=ui_url,
        child_pid=None,
    )


class _FlipHandler(BaseHTTPRequestHandler):
    """200 with EMPTY body until the shared flag flips; then full HTML."""

    serve_html = False

    def log_message(self, *args) -> None:  # silence
        pass

    def do_GET(self) -> None:  # noqa: N802
        if type(self).serve_html:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(HTML)))
            self.end_headers()
            self.wfile.write(HTML)
        else:
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()


def _server_with_delay(handler_cls, delay_seconds: float) -> tuple[str, ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)

    def _delayed_start() -> None:
        if delay_seconds:
            time.sleep(delay_seconds)
        server.serve_forever()

    thread = threading.Thread(target=_delayed_start, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_address[1]}", server


def test_gate_returns_immediately_when_ui_serves(tmp_path: Path):
    class _HtmlHandler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(HTML)))
            self.end_headers()
            self.wfile.write(HTML)

    url, server = _server_with_delay(_HtmlHandler, 0)
    try:
        runtime = ExecutablePluginRuntime(ui_ready_timeout=5.0)
        started = time.monotonic()
        runtime._wait_ui_ready(_handle(url), poll_interval=0.05)
        assert time.monotonic() - started < 2.0
    finally:
        server.shutdown()


def test_gate_waits_for_slow_ui_to_start(tmp_path: Path):
    class _HtmlHandler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(HTML)))
            self.end_headers()
            self.wfile.write(HTML)

    url, server = _server_with_delay(_HtmlHandler, 1.2)
    try:
        runtime = ExecutablePluginRuntime(ui_ready_timeout=15.0)
        started = time.monotonic()
        runtime._wait_ui_ready(_handle(url), poll_interval=0.05)
        elapsed = time.monotonic() - started
        assert elapsed >= 1.1  # truly waited for the slow boot
        assert elapsed < 10.0
    finally:
        server.shutdown()


def test_gate_times_out_when_ui_never_serves(tmp_path: Path):
    # A port that listens for nothing: take one and close it.
    import socket

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
    probe.close()

    runtime = ExecutablePluginRuntime(ui_ready_timeout=0.6)
    started = time.monotonic()
    with pytest.raises(RuntimeError) as excinfo:
        runtime._wait_ui_ready(_handle(f"http://127.0.0.1:{dead_port}/"), poll_interval=0.05)
    elapsed = time.monotonic() - started
    assert "did not become ready within" in str(excinfo.value)
    assert 0.5 <= elapsed < 5.0


def test_gate_rejects_empty_body_until_first_render(tmp_path: Path):
    handler = _FlipHandler
    url, server = _server_with_delay(handler, 0)
    try:
        runtime = ExecutablePluginRuntime(ui_ready_timeout=10.0)

        def _flip_later() -> None:
            time.sleep(1.0)
            handler.serve_html = True

        thread = threading.Thread(target=_flip_later, daemon=True)
        thread.start()
        started = time.monotonic()
        runtime._wait_ui_ready(_handle(url), poll_interval=0.05)
        elapsed = time.monotonic() - started
        assert elapsed >= 0.9  # empty-body responses did NOT count as ready
        assert elapsed < 8.0
    finally:
        server.shutdown()


def test_gate_strips_query_params_when_polling(tmp_path: Path):
    """The panel's uiUrl carries ?cwd=...; readiness polling must hit the bare
    path (the test server only answers '/' — a query would 404 and time out)."""

    class _RootOnlyHandler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self.send_response(200)
                self.send_header("Content-Length", str(len(HTML)))
                self.end_headers()
                self.wfile.write(HTML)
            else:
                self.send_response(404)
                self.end_headers()

    url, server = _server_with_delay(_RootOnlyHandler, 0)
    try:
        runtime = ExecutablePluginRuntime(ui_ready_timeout=5.0)
        runtime._wait_ui_ready(_handle(f"{url}?cwd=%2Fwork%2Fproject"), poll_interval=0.05)
    finally:
        server.shutdown()

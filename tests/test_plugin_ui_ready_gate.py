"""V30 UI-ready gate (+ P1-6③ extension): enable/restart must not report
success until the plugin UI (pi-web) actually serves a rendered, non-empty
document — not merely until the UI port answers any HTTP status (the
launcher's own readiness wait only proves that). P1-6③ added two stages:
an optional manifest ``ui.healthProbe`` (priority when declared) and a
first-``/_next/static/``-chunk check (the Next.js shell can arrive before
its chunks — hydrating against a 404 chunk IS the blank-panel bug).

These unit tests drive ``ExecutablePluginRuntime._wait_ui_ready`` against
local loopback HTTP servers (same pattern as the acquisition tests).
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from mikazuki.plugin_host.runtime import ExecutablePluginRuntime, _ProcessHandle

HTML = b"<!doctype html><html><head><title>pi-web</title></head><body><div id=\"root\"></div></body></html>"

# A Next.js-style shell: the document references a static chunk.
NEXT_HTML_TEMPLATE = (
    b"<!doctype html><html><head>"
    b'<script src="/_next/static/chunks/webpack.js"></script>'
    b'<link href="/_next/static/css/app.css" rel="stylesheet">'
    b"</head><body><div id=\"__next\"></div></body></html>"
)


class _StubProcess:
    """_wait_ui_ready only reads handle.ui_url; the process is never touched."""

    def poll(self):  # pragma: no cover - not exercised by the gate
        return None


def _handle(ui_url: str, *, manifest=None) -> _ProcessHandle:
    return _ProcessHandle(
        process=_StubProcess(),  # type: ignore[arg-type]
        version="0.0.0",
        protocol_version="1",
        port=urlsplit(ui_url).port,  # type: ignore[arg-type]
        token="t" * 40,
        host_tool_token="h" * 40,
        ui_url=ui_url,
        child_pid=None,
        manifest=manifest,
    )


def _manifest_with_probe(health_probe: str | None) -> SimpleNamespace:
    """Minimal RuntimeManifest stand-in: the gate only reads .ui.health_probe."""
    return SimpleNamespace(ui=SimpleNamespace(health_probe=health_probe))


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


# ---------------------------------------------------------------------------
# P1-6③: first-static-chunk gate + manifest healthProbe priority
# ---------------------------------------------------------------------------


class _NextHandler(BaseHTTPRequestHandler):
    """Serves a Next.js-style shell at '/' whose first chunk is 404 until
    ``chunks_up`` flips (simulating pi-web serving the HTML shell before its
    static chunks are reachable — the rc.4 blank-panel window)."""

    chunks_up = False
    chunk_status = 404

    def log_message(self, *args) -> None:  # silence
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(NEXT_HTML_TEMPLATE)))
            self.end_headers()
            self.wfile.write(NEXT_HTML_TEMPLATE)
        elif self.path == "/_next/static/chunks/webpack.js":
            self.send_response(200 if type(self).chunks_up else type(self).chunk_status)
            self.send_header("Content-Length", str(len(b"/* chunk */") if type(self).chunks_up else 0))
            self.end_headers()
            if type(self).chunks_up:
                self.wfile.write(b"/* chunk */")
        else:
            self.send_response(404)
            self.end_headers()


def test_chunk_gate_waits_until_first_chunk_serves(tmp_path: Path):
    """The HTML shell alone is NOT ready: the gate holds until the first
    referenced /_next/static chunk answers 200 (the blank-panel window)."""
    handler = _NextHandler
    url, server = _server_with_delay(handler, 0)
    try:
        runtime = ExecutablePluginRuntime(ui_ready_timeout=10.0)

        def _flip_later() -> None:
            time.sleep(1.0)
            handler.chunks_up = True

        thread = threading.Thread(target=_flip_later, daemon=True)
        thread.start()
        started = time.monotonic()
        runtime._wait_ui_ready(_handle(url), poll_interval=0.05)
        elapsed = time.monotonic() - started
        assert elapsed >= 0.9  # the 404-ing chunk did NOT count as ready
        assert elapsed < 8.0
    finally:
        server.shutdown()
        handler.chunks_up = False


def test_chunk_gate_returns_immediately_when_chunk_serves(tmp_path: Path):
    handler = _NextHandler
    handler.chunks_up = True
    url, server = _server_with_delay(handler, 0)
    try:
        runtime = ExecutablePluginRuntime(ui_ready_timeout=5.0)
        started = time.monotonic()
        runtime._wait_ui_ready(_handle(url), poll_interval=0.05)
        assert time.monotonic() - started < 2.0
    finally:
        server.shutdown()
        handler.chunks_up = False


def test_non_next_document_skips_chunk_gate(tmp_path: Path):
    """Classic non-Next UIs (no /_next/static reference) keep the V30
    document-only semantics — no chunk probe, no new failure mode."""
    handler = _NextHandler  # only used to prove the probe is path-driven...
    del handler

    class _PlainHandler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self.send_response(200)
                self.send_header("Content-Length", str(len(HTML)))
                self.end_headers()
                self.wfile.write(HTML)
            else:
                self.send_response(404)  # any chunk probe would fail here
                self.end_headers()

    url, server = _server_with_delay(_PlainHandler, 0)
    try:
        runtime = ExecutablePluginRuntime(ui_ready_timeout=5.0)
        runtime._wait_ui_ready(_handle(url), poll_interval=0.05)  # returns: no chunk ref
    finally:
        server.shutdown()


def test_manifest_health_probe_takes_priority(tmp_path: Path):
    """With ui.healthProbe declared, the gate waits for the plugin's own
    readiness endpoint BEFORE accepting the (already-served) document."""

    class _ProbeHandler(BaseHTTPRequestHandler):
        healthy = False

        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self.send_response(200 if type(self).healthy else 503)
                self.send_header("Content-Length", str(2 if type(self).healthy else 0))
                self.end_headers()
                if type(self).healthy:
                    self.wfile.write(b"ok")
            elif self.path == "/":
                self.send_response(200)
                self.send_header("Content-Length", str(len(HTML)))
                self.end_headers()
                self.wfile.write(HTML)
            else:
                self.send_response(404)
                self.end_headers()

    url, server = _server_with_delay(_ProbeHandler, 0)
    try:
        runtime = ExecutablePluginRuntime(ui_ready_timeout=10.0)

        def _flip_later() -> None:
            time.sleep(1.0)
            _ProbeHandler.healthy = True

        thread = threading.Thread(target=_flip_later, daemon=True)
        thread.start()
        started = time.monotonic()
        runtime._wait_ui_ready(
            _handle(url, manifest=_manifest_with_probe("/health")), poll_interval=0.05
        )
        elapsed = time.monotonic() - started
        assert elapsed >= 0.9  # the 503 probe held the gate despite the document
        assert elapsed < 8.0
    finally:
        server.shutdown()
        _ProbeHandler.healthy = False


def test_health_probe_timeout_reports_probe_error(tmp_path: Path):
    class _AlwaysDownProbeHandler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Length", str(len(HTML)))
                self.end_headers()
                self.wfile.write(HTML)

    url, server = _server_with_delay(_AlwaysDownProbeHandler, 0)
    try:
        runtime = ExecutablePluginRuntime(ui_ready_timeout=0.6)
        with pytest.raises(RuntimeError) as excinfo:
            runtime._wait_ui_ready(
                _handle(url, manifest=_manifest_with_probe("/health")), poll_interval=0.05
            )
        assert "health probe" in str(excinfo.value)
    finally:
        server.shutdown()


def test_first_static_asset_url_parsing():
    origin = "http://127.0.0.1:5980"
    html = NEXT_HTML_TEMPLATE.decode()
    # The FIRST reference in document order wins (the webpack chunk, before
    # the css link).
    assert ExecutablePluginRuntime._first_static_asset_url(html, origin) == (
        origin + "/_next/static/chunks/webpack.js"
    )
    # Absolute references pass through; non-Next documents yield None.
    assert (
        ExecutablePluginRuntime._first_static_asset_url(
            '<script src="https://cdn.example.com/_next/static/chunks/a.js"></script>', origin
        )
        == "https://cdn.example.com/_next/static/chunks/a.js"
    )
    assert ExecutablePluginRuntime._first_static_asset_url(HTML.decode(), origin) is None
    assert ExecutablePluginRuntime._first_static_asset_url("<html></html>", origin) is None

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from fastapi import FastAPI

import gui
from mikazuki.app import application, proxy
from mikazuki.startup_settings import port_available, resolve_startup


@pytest.fixture
def backend():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.command, self.path))
            if self.path.startswith("/static/monitor.js"):
                content, kind = b'fetch("/api/status?ts=1");', "application/javascript"
            elif self.path.startswith("/static/monitor.css"):
                content, kind = b"body { color: red; }", "text/css"
            elif self.path.startswith("/api/status"):
                content, kind = (
                    b'{"previews":[{"url":"/preview-image?path=a%20b.png"}],'
                    b'"log_lines":["/preview-image is mentioned in a log"]}', "application/json",
                )
            elif self.path.startswith("/preview-image"):
                content, kind = b"image-bytes", "image/png"
            else:
                content, kind = (
                    b'<link href="/static/monitor.css"><script src="/static/monitor.js"></script>'
                    b'<img src="/assets/logo.png"><link href="/favicon.ico">',
                    "text/html",
                )
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        do_POST = do_GET

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request(path, method="GET", app=None):
    if app is None:
        app = FastAPI()
        app.include_router(proxy.router)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://remote-gui.example:28000"
        ) as client:
            return await client.request(method, path)
    return asyncio.run(run())


@pytest.mark.parametrize("path", ["/proxy/tensorboard/data/runs", "/font-roboto/font.woff2"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_disabled_tensorboard_never_contacts_occupied_listener(backend, monkeypatch, path, method):
    port, requests = backend
    settings = {"startup": {"tensorboard": {"enabled": True, "port": port},
                            "monitor": {"enabled": False}}}
    config = resolve_startup(settings, gui.parser.parse_args([]),
                             probe=lambda host, candidate: port_available(host, candidate) if candidate == port else True)
    assert not config.tensorboard.enabled
    monkeypatch.setenv("MIKAZUKI_TENSORBOARD_ENABLED", "0")
    monkeypatch.setenv("MIKAZUKI_TENSORBOARD_HOST", "127.0.0.1")
    monkeypatch.setenv("MIKAZUKI_TENSORBOARD_PORT", str(port))
    response = request(path, method)
    assert response.status_code == 503
    assert "disabled" in response.text.lower()
    assert requests == []


def test_monitor_json_preserves_non_url_status_text(backend, monkeypatch):
    port, _ = backend
    monkeypatch.setenv("TRAIN_MONITOR_ENABLED", "1")
    monkeypatch.setenv("TRAIN_MONITOR_PORT", str(port))
    status = request("/train-monitor/api/status").json()
    assert status["log_lines"] == ["/preview-image is mentioned in a log"]


def test_enabled_tensorboard_uses_runtime_endpoint(backend, monkeypatch):
    port, requests = backend
    monkeypatch.setenv("MIKAZUKI_TENSORBOARD_ENABLED", "1")
    monkeypatch.setenv("MIKAZUKI_TENSORBOARD_HOST", "127.0.0.1")
    monkeypatch.setenv("MIKAZUKI_TENSORBOARD_PORT", str(port))
    response = request("/proxy/tensorboard/data/runs?x=1", "POST")
    assert response.status_code == 200
    assert requests == [("POST", "/data/runs?x=1")]


def test_monitor_stays_on_gui_origin_and_proxies_all_resources(backend, monkeypatch):
    port, requests = backend
    monkeypatch.setenv("TRAIN_MONITOR_ENABLED", "1")
    monkeypatch.setenv("TRAIN_MONITOR_HOST", "0.0.0.0")
    monkeypatch.setenv("TRAIN_MONITOR_PORT", str(port))
    redirect = request("/train-monitor")
    assert redirect.status_code in (302, 307)
    assert redirect.headers["location"] == "/train-monitor/"
    page = request("/train-monitor/")
    assert page.status_code == 200
    assert 'href="/train-monitor/static/monitor.css"' in page.text
    assert 'src="/train-monitor/static/monitor.js"' in page.text
    assert 'src="/train-monitor/assets/logo.png"' in page.text
    assert 'href="/train-monitor/favicon.ico"' in page.text
    script = request("/train-monitor/static/monitor.js")
    assert 'fetch("/train-monitor/api/status?ts=1")' in script.text
    assert request("/train-monitor/static/monitor.css").status_code == 200
    status = request("/train-monitor/api/status?ts=1")
    assert status.json()["previews"][0]["url"] == "/train-monitor/preview-image?path=a%20b.png"
    preview = request(status.json()["previews"][0]["url"])
    assert preview.content == b"image-bytes"
    assert ("GET", "/preview-image?path=a%20b.png") in requests
    assert ("GET", "/api/status?ts=1") in requests


def test_disabled_monitor_does_not_contact_foreign_listener(backend, monkeypatch):
    port, requests = backend
    monkeypatch.setenv("TRAIN_MONITOR_ENABLED", "0")
    monkeypatch.setenv("TRAIN_MONITOR_PORT", str(port))
    assert request("/train-monitor/").status_code == 503
    assert request("/train-monitor/api/status").status_code == 503
    assert requests == []


def test_application_monitor_entrypoint_uses_same_origin_proxy(backend, monkeypatch):
    port, _ = backend
    monkeypatch.setenv("TRAIN_MONITOR_ENABLED", "1")
    monkeypatch.setenv("TRAIN_MONITOR_PORT", str(port))
    response = request("/train-monitor", app=application.app)
    assert response.headers["location"] == "/train-monitor/"
    assert request("/train-monitor/api/status", app=application.app).status_code == 200


def test_tensorboard_missing_enable_flag_fails_closed(backend, monkeypatch):
    port, requests = backend
    monkeypatch.delenv("MIKAZUKI_TENSORBOARD_ENABLED", raising=False)
    monkeypatch.setenv("MIKAZUKI_TENSORBOARD_PORT", str(port))
    assert request("/proxy/tensorboard/data/runs", "POST").status_code == 503
    assert requests == []

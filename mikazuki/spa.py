import os
import socket
import time
from pathlib import PurePosixPath
from urllib.parse import urlsplit, urlunsplit


STATIC_PREFIXES = ("assets/", "font-roboto/")


def train_monitor_url(request_url: str, port: int) -> str:
    """Build a monitor URL on the same host the browser used for the GUI."""
    parsed = urlsplit(request_url)
    host = parsed.hostname or "127.0.0.1"
    if ":" in host:
        host = f"[{host}]"
    return urlunsplit(("http", f"{host}:{port}", "/", "", ""))


def train_monitor_enabled() -> bool:
    """True only when gui.py actually spawned the train monitor process."""
    return os.environ.get("TRAIN_MONITOR_ENABLED", "0").strip() == "1"


def train_monitor_browser_host() -> str:
    host = (os.environ.get("TRAIN_MONITOR_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    if host in ("0.0.0.0", "::", "[::]"):
        return "127.0.0.1"
    return host


def train_monitor_browser_url() -> str | None:
    """Local URL for the optional startup browser tab, or None if disabled."""
    if not train_monitor_enabled():
        return None
    port = int(os.environ.get("TRAIN_MONITOR_PORT", "6008"))
    return f"http://{train_monitor_browser_host()}:{port}/"


def wait_for_tcp_port(host: str, port: int, timeout: float = 10.0, interval: float = 0.2) -> bool:
    """Return True once a TCP accept is possible, else False after timeout."""
    deadline = time.monotonic() + max(0.0, timeout)
    while time.monotonic() <= deadline:
        try:
            with socket.create_connection((host, port), timeout=min(interval, 1.0)):
                return True
        except OSError:
            time.sleep(interval)
    return False


def should_fallback_to_spa(path: str, status_code: int) -> bool:
    """Return whether a missing request is a client-side navigation route."""
    normalized = str(PurePosixPath(path.lstrip("/")))
    if status_code != 404 or normalized.startswith(STATIC_PREFIXES):
        return False
    return not PurePosixPath(normalized).suffix or normalized.endswith(".html")

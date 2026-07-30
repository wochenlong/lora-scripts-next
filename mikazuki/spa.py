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


def should_fallback_to_spa(path: str, status_code: int) -> bool:
    """Return whether a missing request is a client-side navigation route."""
    normalized = str(PurePosixPath(path.lstrip("/")))
    if status_code != 404 or normalized.startswith(STATIC_PREFIXES):
        return False
    return not PurePosixPath(normalized).suffix or normalized.endswith(".html")

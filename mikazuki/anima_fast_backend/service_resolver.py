from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os


DEFAULT_GUI_PORT = str(280 * 100)


@dataclass(frozen=True)
class ServiceEndpoint:
    service_id: str
    public_path: str
    public_url: str
    internal_url: str | None = None
    status: str = "unknown"


class ServiceResolverError(RuntimeError):
    pass


def _display_host(host: str | None) -> str:
    if not host or host in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return host


def _join_public(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


class LegacyServiceResolverShim:
    """Compatibility layer until governed service registry is available."""

    def __init__(self, env: dict[str, str] | None = None):
        self.env = env or os.environ

    def public_base_url(self) -> str:
        host = _display_host(self.env.get("MIKAZUKI_HOST", "127.0.0.1"))
        port = self.env.get("MIKAZUKI_PORT", DEFAULT_GUI_PORT)
        return f"http://{host}:{port}"

    def api(self) -> ServiceEndpoint:
        base = self.public_base_url()
        host = _display_host(self.env.get("MIKAZUKI_HOST", "127.0.0.1"))
        port = self.env.get("MIKAZUKI_PORT", DEFAULT_GUI_PORT)
        return ServiceEndpoint("api", "/api/", _join_public(base, "/api/"), f"http://{host}:{port}/api", "legacy")

    def train_monitor(self) -> ServiceEndpoint:
        base = self.public_base_url()
        return ServiceEndpoint("train-monitor", "/monitor/", _join_public(base, "/monitor/"), None, "legacy")

    def tensorboard(self) -> ServiceEndpoint:
        base = self.public_base_url()
        return ServiceEndpoint("tensorboard", "/tensorboard/", _join_public(base, "/tensorboard/"), None, "legacy")

    def train_log_viewer_url(self, task_id: str) -> str:
        return _join_public(self.public_base_url(), f"/train-log?task_id={task_id}")

    def train_log_stream_path(self, task_id: str) -> str:
        return f"/api/train/log/stream/{task_id}"


class RegistryServiceResolver:
    """Resolver for future `.runtime/services.json` service registry."""

    def __init__(self, registry_path: Path):
        self.registry_path = registry_path
        self._data = self._load()

    def _load(self) -> dict:
        if not self.registry_path.is_file():
            raise ServiceResolverError(f"services registry does not exist: {self.registry_path}")
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _service(self, service_id: str) -> ServiceEndpoint:
        services = self._data.get("services", {})
        raw = services.get(service_id)
        if not isinstance(raw, dict):
            raise ServiceResolverError(f"service not registered: {service_id}")
        return ServiceEndpoint(
            service_id=service_id,
            public_path=raw.get("public_path", ""),
            public_url=raw.get("public_url", ""),
            internal_url=raw.get("internal_url"),
            status=raw.get("status", "unknown"),
        )

    def public_base_url(self) -> str:
        return self._data.get("public_base_url") or self._data.get("gateway", {}).get("public_url", "")

    def api(self) -> ServiceEndpoint:
        return self._service("api")

    def train_monitor(self) -> ServiceEndpoint:
        return self._service("train-monitor")

    def tensorboard(self) -> ServiceEndpoint:
        return self._service("tensorboard")

    def train_log_viewer_url(self, task_id: str) -> str:
        return _join_public(self.public_base_url(), f"/train-log?task_id={task_id}")

    def train_log_stream_path(self, task_id: str) -> str:
        return f"/api/train/log/stream/{task_id}"


def default_resolver(root: Path | None = None):
    root = (root or Path.cwd()).resolve()
    registry = root / ".runtime" / "services.json"
    if registry.is_file():
        return RegistryServiceResolver(registry)
    return LegacyServiceResolverShim()

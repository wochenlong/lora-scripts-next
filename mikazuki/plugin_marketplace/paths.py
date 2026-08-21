from __future__ import annotations

import re
from pathlib import Path


_PLUGIN_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62})$")
_VERSION = re.compile(r"^[0-9A-Za-z](?:[0-9A-Za-z._-]{0,63})$")


class PathPolicyError(ValueError):
    pass


def _safe_identifier(value: str, pattern: re.Pattern[str], label: str) -> str:
    if not value or not pattern.fullmatch(value) or ".." in value:
        raise PathPolicyError(f"unsafe {label}: {value!r}")
    return value


class MarketplacePaths:
    def __init__(self, root: Path):
        self.root = root.resolve()

    @property
    def registry_file(self) -> Path:
        return self.root / "registry.json"

    @property
    def packages_root(self) -> Path:
        return self.root / "plugins"

    @property
    def staging_root(self) -> Path:
        return self.root / ".staging"

    @property
    def quarantine_root(self) -> Path:
        return self.root / ".quarantine"

    @property
    def cache_root(self) -> Path:
        return self.root / "cache"

    @property
    def data_root(self) -> Path:
        return self.root / "data"

    def plugin_root(self, plugin_id: str) -> Path:
        plugin_id = _safe_identifier(plugin_id, _PLUGIN_ID, "plugin id")
        return self._contained(self.packages_root / plugin_id)

    def plugin_versions(self, plugin_id: str) -> Path:
        return self.plugin_root(plugin_id) / "versions"

    def version_dir(self, plugin_id: str, version: str) -> Path:
        version = _safe_identifier(version, _VERSION, "version")
        return self._contained(self.plugin_versions(plugin_id) / version)

    def staging_dir(self, plugin_id: str, version: str, operation_id: str) -> Path:
        plugin_id = _safe_identifier(plugin_id, _PLUGIN_ID, "plugin id")
        version = _safe_identifier(version, _VERSION, "version")
        operation_id = _safe_identifier(operation_id, _VERSION, "operation id")
        return self._contained(self.staging_root / plugin_id / version / operation_id)

    def cache_dir(self, plugin_id: str) -> Path:
        plugin_id = _safe_identifier(plugin_id, _PLUGIN_ID, "plugin id")
        return self._contained(self.cache_root / plugin_id)

    def user_data_dir(self, plugin_id: str) -> Path:
        plugin_id = _safe_identifier(plugin_id, _PLUGIN_ID, "plugin id")
        return self._contained(self.data_root / plugin_id)

    def quarantine_package(self, plugin_id: str, version: str) -> Path:
        plugin_id = _safe_identifier(plugin_id, _PLUGIN_ID, "plugin id")
        version = _safe_identifier(version, _VERSION, "version")
        return self._contained(self.quarantine_root / plugin_id / f"{version}.zip")

    def _contained(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise PathPolicyError(f"path escapes marketplace root: {resolved}") from exc
        return resolved

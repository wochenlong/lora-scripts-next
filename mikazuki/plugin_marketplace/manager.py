from __future__ import annotations

import shutil
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath

from .models import MarketplaceEntry, PluginManifest, PluginStatus
from .package import PackageLimits, PackageValidationError, extract_package, inspect_package, validate_manifest_entry
from .paths import MarketplacePaths
from .store import MarketplaceStore
from .trust import TrustStore, version_satisfies


HealthCheck = Callable[[PluginManifest, Path], bool]


class MarketplaceManager:
    def __init__(
        self,
        *,
        paths: MarketplacePaths,
        store: MarketplaceStore,
        trust: TrustStore,
        host_version: str,
        platform: str,
        protocol_version: str = "1",
        health_check: HealthCheck | None = None,
        package_limits: PackageLimits | None = None,
    ):
        self.paths = paths
        self.store = store
        self.trust = trust
        self.host_version = host_version
        self.platform = platform
        self.protocol_version = protocol_version
        self.health_check = health_check or self._default_health
        self.package_limits = package_limits or PackageLimits()
        self._guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}

    def _plugin_lock(self, plugin_id: str) -> threading.RLock:
        self.paths.plugin_root(plugin_id)  # validate before allocating a lock
        with self._guard:
            return self._locks.setdefault(plugin_id, threading.RLock())

    @staticmethod
    def _default_health(manifest: PluginManifest, directory: Path) -> bool:
        return (directory / manifest.runtime.entrypoint).is_file() and (directory / manifest.ui.entrypoint).is_file()

    def status(self, plugin_id: str) -> PluginStatus:
        self.paths.plugin_root(plugin_id)
        record = self.store.get_plugin(plugin_id)
        if record is None:
            return PluginStatus(id=plugin_id, state="not_installed")
        versions = record.get("versions") or {}
        active = record.get("active_version")
        if not active or active not in versions or not self.paths.version_dir(plugin_id, active).is_dir():
            return PluginStatus(
                id=plugin_id,
                state="broken",
                active_version=active,
                previous_version=record.get("previous_version"),
                enabled=False,
                installed_versions=sorted(versions),
                reason="active version is missing",
            )
        enabled = bool(record.get("enabled"))
        return PluginStatus(
            id=plugin_id,
            state="enabled" if enabled else "installed",
            active_version=active,
            previous_version=record.get("previous_version"),
            enabled=enabled,
            installed_versions=sorted(versions),
        )

    def list_statuses(self) -> list[PluginStatus]:
        plugin_ids = sorted(self.store.snapshot()["plugins"])
        return [self.status(plugin_id) for plugin_id in plugin_ids]

    def enabled_extensions(self) -> list[dict]:
        extensions: list[dict] = []
        for status in self.list_statuses():
            if not status.enabled or not status.active_version:
                continue
            record = self.store.get_plugin(status.id) or {}
            version_record = (record.get("versions") or {}).get(status.active_version)
            if not version_record:
                continue
            manifest = PluginManifest.model_validate(version_record["manifest"])
            extensions.append(
                {
                    "pluginId": status.id,
                    "displayName": version_record.get("name") or status.id,
                    "version": status.active_version,
                    "enabled": True,
                    "state": "ready",
                    # Bridge request capabilities are granted by the host
                    # permission gateway in Phase 1.2, not copied from the
                    # manifest's high-level capability labels.
                    "capabilities": [],
                    "ui": {
                        **(
                            {
                                "floatingPanel": {
                                    "entryUrl": (
                                        f"/api/plugin-host/ui/{status.id}/{status.active_version}/"
                                        f"{PurePosixPath(manifest.ui.entrypoint).name}"
                                    )
                                }
                            }
                            if "floating-panel" in manifest.ui.placements
                            else {}
                        ),
                        **({"artifactDetail": True} if "artifact-detail" in manifest.ui.placements else {}),
                    },
                }
            )
        return extensions

    def ui_artifact(self, plugin_id: str, version: str, asset_path: str) -> Path:
        status = self.status(plugin_id)
        if not status.enabled or status.active_version != version:
            raise PermissionError("plugin UI is not enabled for the requested version")
        record = self._required_record(plugin_id)
        version_record = (record.get("versions") or {}).get(version)
        if not version_record:
            raise FileNotFoundError("plugin version is not installed")
        manifest = PluginManifest.model_validate(version_record["manifest"])
        relative = PurePosixPath(asset_path)
        if (
            not asset_path
            or "\\" in asset_path
            or relative.is_absolute()
            or ".." in relative.parts
            or any(":" in part for part in relative.parts)
        ):
            raise ValueError("unsafe plugin artifact path")
        version_root = self.paths.version_dir(plugin_id, version)
        ui_relative = PurePosixPath(manifest.ui.entrypoint).parent
        ui_root = (version_root / Path(*ui_relative.parts)).resolve()
        try:
            ui_root.relative_to(version_root)
        except ValueError as exc:
            raise ValueError("plugin UI root escapes the installed version") from exc
        artifact = (ui_root / Path(*relative.parts)).resolve()
        try:
            artifact.relative_to(ui_root)
        except ValueError as exc:
            raise ValueError("unsafe plugin artifact path") from exc
        if not artifact.is_file():
            raise FileNotFoundError("plugin UI artifact was not found")
        return artifact

    def install(self, entry: MarketplaceEntry, package_path: Path) -> PluginStatus:
        with self._plugin_lock(entry.id):
            if package_path.is_file() and package_path.stat().st_size > self.package_limits.max_package_bytes:
                raise PackageValidationError("package size limit exceeded")
            self.trust.verify(entry, package_path)
            self.trust.verify_compatibility(entry, host_version=self.host_version, platform=self.platform)
            manifest, members = inspect_package(package_path, self.package_limits)
            validate_manifest_entry(manifest, entry)
            if manifest.protocol_version != self.protocol_version:
                raise ValueError(f"unsupported plugin protocol: {manifest.protocol_version}")
            if not version_satisfies(self.host_version, manifest.host_compatibility):
                raise ValueError(f"manifest is incompatible with host {self.host_version}")

            operation_id = uuid.uuid4().hex
            staging = self.paths.staging_dir(entry.id, entry.latest_version, operation_id)
            target = self.paths.version_dir(entry.id, entry.latest_version)
            record = self.store.get_plugin(entry.id) or {
                "active_version": None,
                "previous_version": None,
                "enabled": False,
                "versions": {},
            }
            previous_active = record.get("active_version")
            previous_enabled = bool(record.get("enabled"))
            try:
                extract_package(package_path, staging, members)
                if not self.health_check(manifest, staging):
                    raise RuntimeError(f"plugin health check failed: {entry.id}@{entry.latest_version}")
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    existing = (record.get("versions") or {}).get(entry.latest_version)
                    if not existing or existing.get("sha256") != entry.sha256:
                        raise RuntimeError(
                            f"immutable plugin version already exists with different content: "
                            f"{entry.id}@{entry.latest_version}"
                        )
                    shutil.rmtree(staging)
                else:
                    staging.replace(target)
                versions = dict(record.get("versions") or {})
                versions[entry.latest_version] = {
                    "name": entry.name,
                    "manifest": manifest.model_dump(mode="json", by_alias=True),
                    "sha256": entry.sha256,
                    "installed_at": datetime.now(timezone.utc).isoformat(),
                }
                record.update(
                    {
                        "active_version": entry.latest_version,
                        "previous_version": previous_active if previous_active != entry.latest_version else record.get("previous_version"),
                        # A clean install is always disabled.  An already-enabled
                        # plugin remains enabled across a verified side-by-side update.
                        "enabled": previous_enabled if previous_active else False,
                        "versions": versions,
                    }
                )
                self.store.set_plugin(entry.id, record)
            finally:
                if staging.exists():
                    shutil.rmtree(staging, ignore_errors=True)
                parent = staging.parent
                while parent != self.paths.staging_root and parent.exists():
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
            return self.status(entry.id)

    def enable(self, plugin_id: str) -> PluginStatus:
        with self._plugin_lock(plugin_id):
            record = self._required_record(plugin_id)
            manifest, directory = self._active_manifest(plugin_id, record)
            if not self.health_check(manifest, directory):
                raise RuntimeError(f"plugin health check failed: {plugin_id}@{manifest.version}")
            record["enabled"] = True
            self.store.set_plugin(plugin_id, record)
            return self.status(plugin_id)

    def disable(self, plugin_id: str) -> PluginStatus:
        with self._plugin_lock(plugin_id):
            record = self._required_record(plugin_id)
            record["enabled"] = False
            self.store.set_plugin(plugin_id, record)
            return self.status(plugin_id)

    def rollback(self, plugin_id: str, version: str | None = None) -> PluginStatus:
        with self._plugin_lock(plugin_id):
            record = self._required_record(plugin_id)
            current = record.get("active_version")
            target_version = version or record.get("previous_version")
            if not target_version or target_version not in (record.get("versions") or {}):
                raise ValueError(f"rollback version is not installed: {target_version}")
            manifest = PluginManifest.model_validate(record["versions"][target_version]["manifest"])
            directory = self.paths.version_dir(plugin_id, target_version)
            if not directory.is_dir() or not self.health_check(manifest, directory):
                raise RuntimeError(f"rollback health check failed: {plugin_id}@{target_version}")
            record["active_version"] = target_version
            record["previous_version"] = current
            self.store.set_plugin(plugin_id, record)
            return self.status(plugin_id)

    def uninstall(self, plugin_id: str, *, delete_user_data: bool = False) -> PluginStatus:
        with self._plugin_lock(plugin_id):
            plugin_root = self.paths.plugin_root(plugin_id)
            cache = self.paths.cache_dir(plugin_id)
            if plugin_root.exists():
                shutil.rmtree(plugin_root)
            if cache.exists():
                shutil.rmtree(cache)
            if delete_user_data:
                data = self.paths.user_data_dir(plugin_id)
                if data.exists():
                    shutil.rmtree(data)
            self.store.remove_plugin(plugin_id)
            return PluginStatus(id=plugin_id, state="not_installed")

    def _required_record(self, plugin_id: str) -> dict:
        record = self.store.get_plugin(plugin_id)
        if record is None:
            raise ValueError(f"plugin is not installed: {plugin_id}")
        return record

    def _active_manifest(self, plugin_id: str, record: dict) -> tuple[PluginManifest, Path]:
        active = record.get("active_version")
        version_record = (record.get("versions") or {}).get(active)
        if not active or not version_record:
            raise RuntimeError(f"plugin active version is missing: {plugin_id}")
        return PluginManifest.model_validate(version_record["manifest"]), self.paths.version_dir(plugin_id, active)

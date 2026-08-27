from __future__ import annotations

import copy
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath

from mikazuki.plugin_host.broker import PluginBridgeMethod, PluginCapabilityContext
from mikazuki.plugin_host.runtime import PluginRuntimeController, RuntimeSnapshot

from .models import MarketplaceEntry, PluginManifest, PluginStatus
from .package import (
    PackageLimits,
    PackageValidationError,
    extract_package,
    inspect_package,
    remove_tree,
    validate_manifest_entry,
)
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
        runtime: PluginRuntimeController | None = None,
    ):
        self.paths = paths
        self.store = store
        self.trust = trust
        self.host_version = host_version
        self.platform = platform
        self.protocol_version = protocol_version
        self.health_check = health_check or self._default_health
        self.package_limits = package_limits or PackageLimits()
        self.runtime = runtime
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
        runtime = self._runtime_status(plugin_id) if enabled else RuntimeSnapshot(state="stopped")
        runtime_error = enabled and self.runtime is not None and runtime.state != "running"
        return PluginStatus(
            id=plugin_id,
            state="runtime_error" if runtime_error else ("enabled" if enabled else "installed"),
            active_version=active,
            previous_version=record.get("previous_version"),
            enabled=enabled,
            installed_versions=sorted(versions),
            reason=(runtime.reason or record.get("last_runtime_error", "")) if runtime_error else "",
            runtime_state=runtime.state if self.runtime is not None else None,
            runtime_pid=runtime.pid,
            runtime_ui_url=runtime.ui_url if runtime.state == "running" else None,
        )

    def list_statuses(self) -> list[PluginStatus]:
        plugin_ids = sorted(self.store.snapshot()["plugins"])
        return [self.status(plugin_id) for plugin_id in plugin_ids]

    def plugin_for_host_tool_token(self, supplied_token: str) -> str | None:
        """Resolve a per-runtime Host Tool token to its enabled plugin.

        Host Tool traffic intentionally does not carry a plugin id supplied by
        the child process.  The token is the capability, and the runtime
        controller is the only component allowed to validate it.
        """
        if not isinstance(supplied_token, str) or not supplied_token or self.runtime is None:
            return None
        for plugin_id in sorted(self.store.snapshot()["plugins"]):
            try:
                if self.status(plugin_id).enabled and self.runtime.verify_host_tool_token(plugin_id, supplied_token):
                    return plugin_id
            except Exception:
                continue
        return None

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
            granted = frozenset(record.get("granted_permissions") or ())
            bridge_methods = [
                item.method
                for item in (manifest.bridge.requests + manifest.bridge.streams)
                if item.permission in granted
            ]
            if "floating-panel" in manifest.ui.placements:
                if status.runtime_ui_url:
                    # Server-mode UI: the runtime's READY line reported a live
                    # loopback server (e.g. the embedded pi-web). The floating
                    # dialog loads it directly; no host file serving.
                    floating_panel = {"mode": "server", "entryUrl": status.runtime_ui_url}
                else:
                    floating_panel = {
                        "mode": "static",
                        "entryUrl": (
                            f"/api/plugin-host/ui/{status.id}/{status.active_version}/"
                            f"{PurePosixPath(manifest.ui.entrypoint).name}"
                        ),
                    }
            else:
                floating_panel = None
            extensions.append(
                {
                    "pluginId": status.id,
                    "displayName": version_record.get("name") or status.id,
                    "version": status.active_version,
                    "enabled": True,
                    "state": "runtime_error" if status.state == "runtime_error" else "ready",
                    # Only typed bridge methods whose manifest permission was
                    # explicitly granted are projected; high-level capability
                    # labels never authorize a request.
                    "capabilities": sorted(set(bridge_methods)),
                    "ui": {
                        **({"floatingPanel": floating_panel} if floating_panel else {}),
                        **({"artifactDetail": True} if "artifact-detail" in manifest.ui.placements else {}),
                        **(
                            {
                                "settings": {
                                    "entryUrl": (
                                        f"/api/plugin-host/ui/{status.id}/{status.active_version}/"
                                        f"{PurePosixPath(manifest.ui.settings_entrypoint).name}"
                                    )
                                }
                            }
                            if manifest.ui.settings_entrypoint
                            else {}
                        ),
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

    def install(
        self,
        entry: MarketplaceEntry,
        package_path: Path,
        *,
        approved_permissions: set[str] | None = None,
    ) -> PluginStatus:
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
                "granted_permissions": [],
                "versions": {},
            }
            original_record = copy.deepcopy(record)
            previous_active = record.get("active_version")
            previous_enabled = bool(record.get("enabled"))
            previous_grants = set(record.get("granted_permissions") or ())
            manifest_permissions = set(manifest.permissions)
            approved = set(approved_permissions or ())
            if approved and approved != manifest_permissions:
                raise PermissionError("approved permissions must exactly match the plugin manifest")
            if previous_enabled and not manifest_permissions <= previous_grants and approved != manifest_permissions:
                raise PermissionError("plugin update requires approval for changed permissions")
            next_grants = approved if approved else (previous_grants & manifest_permissions)
            target_created = False
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
                    remove_tree(staging)
                else:
                    staging.replace(target)
                    target_created = True
                versions = dict(record.get("versions") or {})
                versions[entry.latest_version] = {
                    "name": entry.name,
                    "manifest": manifest.model_dump(mode="json", by_alias=True),
                    "sha256": entry.sha256,
                    "installed_at": datetime.now(timezone.utc).isoformat(),
                }
                next_record = copy.deepcopy(record)
                next_record.update(
                    {
                        "active_version": entry.latest_version,
                        "previous_version": previous_active if previous_active != entry.latest_version else record.get("previous_version"),
                        # A clean install is always disabled.  An already-enabled
                        # plugin remains enabled across a verified side-by-side update.
                        "enabled": previous_enabled if previous_active else False,
                        "granted_permissions": sorted(next_grants) if previous_active else [],
                        "last_runtime_error": "",
                        "versions": versions,
                    }
                )
                switch_runtime = previous_enabled and previous_active != entry.latest_version
                if switch_runtime:
                    try:
                        self._runtime_stop(entry.id)
                        self.store.set_plugin(entry.id, next_record)
                        self._runtime_start(manifest, target)
                    except Exception as exc:
                        restored = copy.deepcopy(original_record)
                        try:
                            self.store.set_plugin(entry.id, restored)
                            old_manifest, old_directory = self._active_manifest(entry.id, restored)
                            self._runtime_start(old_manifest, old_directory)
                        except Exception:
                            restored["enabled"] = False
                            restored["last_runtime_error"] = "plugin update and rollback runtime activation failed"
                            self.store.set_plugin(entry.id, restored)
                        if target_created:
                            remove_tree(target, ignore_errors=True)
                        raise RuntimeError("plugin update runtime activation failed") from exc
                else:
                    try:
                        self.store.set_plugin(entry.id, next_record)
                    except Exception:
                        if target_created:
                            remove_tree(target, ignore_errors=True)
                        raise
            finally:
                if staging.exists():
                    remove_tree(staging, ignore_errors=True)
                parent = staging.parent
                while parent != self.paths.staging_root and parent.exists():
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
            return self.status(entry.id)

    def enable(self, plugin_id: str, approved_permissions: set[str]) -> PluginStatus:
        with self._plugin_lock(plugin_id):
            record = self._required_record(plugin_id)
            manifest, directory = self._active_manifest(plugin_id, record)
            if set(approved_permissions) != set(manifest.permissions):
                raise PermissionError("enable requires approval for all manifest permissions")
            if not self.health_check(manifest, directory):
                raise RuntimeError(f"plugin health check failed: {plugin_id}@{manifest.version}")
            try:
                self._runtime_start(manifest, directory)
                record["enabled"] = True
                record["granted_permissions"] = sorted(set(approved_permissions))
                record["last_runtime_error"] = ""
                self.store.set_plugin(plugin_id, record)
            except Exception:
                try:
                    self._runtime_stop(plugin_id)
                except Exception:
                    pass
                record["enabled"] = False
                record["last_runtime_error"] = "plugin runtime failed to start"
                self.store.set_plugin(plugin_id, record)
                raise
            return self.status(plugin_id)

    def disable(self, plugin_id: str) -> PluginStatus:
        with self._plugin_lock(plugin_id):
            record = self._required_record(plugin_id)
            record["enabled"] = False
            self.store.set_plugin(plugin_id, record)
            try:
                self._runtime_stop(plugin_id)
            except Exception:
                record["last_runtime_error"] = "plugin runtime failed to stop"
                self.store.set_plugin(plugin_id, record)
                raise
            return self.status(plugin_id)

    def restart(self, plugin_id: str) -> PluginStatus:
        with self._plugin_lock(plugin_id):
            record = self._required_record(plugin_id)
            if not record.get("enabled"):
                raise ValueError(f"plugin is not enabled: {plugin_id}")
            manifest, directory = self._active_manifest(plugin_id, record)
            try:
                self._runtime_stop(plugin_id)
                self._runtime_start(manifest, directory)
                record["last_runtime_error"] = ""
                self.store.set_plugin(plugin_id, record)
            except Exception:
                record["last_runtime_error"] = "plugin runtime failed to restart"
                self.store.set_plugin(plugin_id, record)
                raise
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
            enabled = bool(record.get("enabled"))
            if enabled and target_version != current:
                self._runtime_stop(plugin_id)
                try:
                    self._runtime_start(manifest, directory)
                except Exception as exc:
                    try:
                        current_manifest, current_directory = self._active_manifest(plugin_id, record)
                        self._runtime_start(current_manifest, current_directory)
                    except Exception:
                        record["enabled"] = False
                        record["last_runtime_error"] = "plugin rollback and recovery runtime activation failed"
                        self.store.set_plugin(plugin_id, record)
                    raise RuntimeError("plugin rollback runtime activation failed") from exc
            record["active_version"] = target_version
            record["previous_version"] = current
            record["last_runtime_error"] = ""
            self.store.set_plugin(plugin_id, record)
            return self.status(plugin_id)

    def uninstall(self, plugin_id: str, *, delete_user_data: bool = False) -> PluginStatus:
        with self._plugin_lock(plugin_id):
            plugin_root = self.paths.plugin_root(plugin_id)
            cache = self.paths.cache_dir(plugin_id)
            record = self.store.get_plugin(plugin_id)
            if record is not None:
                record["enabled"] = False
                self.store.set_plugin(plugin_id, record)
            self._runtime_stop(plugin_id)
            if plugin_root.exists():
                remove_tree(plugin_root)
            if cache.exists():
                remove_tree(cache)
            if delete_user_data:
                data = self.paths.user_data_dir(plugin_id)
                if data.exists():
                    remove_tree(data)
            self.store.remove_plugin(plugin_id)
            return PluginStatus(id=plugin_id, state="not_installed")

    def capability_context(self, plugin_id: str) -> PluginCapabilityContext:
        status = self.status(plugin_id)
        if not status.enabled or not status.active_version or status.state in {"broken", "runtime_error"}:
            raise ValueError(f"plugin is not enabled: {plugin_id}")
        record = self._required_record(plugin_id)
        manifest, _ = self._active_manifest(plugin_id, record)
        return PluginCapabilityContext(
            plugin_id=plugin_id,
            version=status.active_version,
            manifest_permissions=frozenset(manifest.permissions),
            granted_permissions=frozenset(record.get("granted_permissions") or ()),
            requests={
                item.method: PluginBridgeMethod(item.permission, item.params_schema)
                for item in manifest.bridge.requests
            },
            streams={
                item.method: PluginBridgeMethod(item.permission, item.params_schema)
                for item in manifest.bridge.streams
            },
        )

    async def capability_request(self, plugin_id: str, request_id: str, method: str, params: dict):
        if self.runtime is None:
            raise RuntimeError("plugin runtime forwarding is unavailable")
        return await self.runtime.request(plugin_id, request_id, method, params)

    async def capability_stream(self, plugin_id: str, request_id: str, method: str, params: dict):
        if self.runtime is None:
            raise RuntimeError("plugin runtime forwarding is unavailable")
        return await self.runtime.stream(plugin_id, request_id, method, params)

    def verify_host_tool_token(self, plugin_id: str, supplied_token: str) -> bool:
        if self.runtime is None:
            return False
        return self.runtime.verify_host_tool_token(plugin_id, supplied_token)

    def _runtime_start(self, manifest: PluginManifest, directory: Path) -> RuntimeSnapshot:
        if self.runtime is None:
            return RuntimeSnapshot(state="running", version=manifest.version, protocol_version=manifest.protocol_version)
        return self.runtime.start(manifest, directory, self.paths.user_data_dir(manifest.id))

    def _runtime_stop(self, plugin_id: str) -> None:
        if self.runtime is not None:
            self.runtime.stop(plugin_id)

    def _runtime_status(self, plugin_id: str) -> RuntimeSnapshot:
        if self.runtime is None:
            return RuntimeSnapshot(state="running")
        try:
            return self.runtime.status(plugin_id)
        except Exception:
            return RuntimeSnapshot(state="crashed", reason="plugin runtime health check failed")

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

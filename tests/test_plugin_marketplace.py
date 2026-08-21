from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from mikazuki.plugin_marketplace.manager import MarketplaceManager
from mikazuki.plugin_marketplace.models import MarketplaceEntry, PluginManifest
from mikazuki.plugin_marketplace.package import PackageLimits, PackageValidationError
from mikazuki.plugin_marketplace.paths import MarketplacePaths, PathPolicyError
from mikazuki.plugin_marketplace.store import MarketplaceStore
from mikazuki.plugin_marketplace.trust import TrustError, TrustStore, canonical_entry_payload


HOST_VERSION = "2.9.2"


def manifest_dict(*, version: str = "0.1.0", install_hooks: list[str] | None = None) -> dict:
    return {
        "id": "next-trainer-pi-agent",
        "publisher": "approved-publisher-id",
        "version": version,
        "protocolVersion": "1",
        "hostCompatibility": ">=2.9.2 <3.0.0",
        "platforms": ["win32-x64"],
        "runtime": {
            "kind": "executable",
            "entrypoint": "bin/next-trainer-pi-sidecar.exe",
            "buildNode": "22.19.0",
            "embeddedRuntime": "bun-1.4.0",
        },
        "ui": {
            "entrypoint": "ui/index.js",
            "extensionApi": "1",
            "placements": ["floating-panel", "artifact-detail"],
        },
        "capabilities": ["session", "events"],
        "permissions": ["model-provider", "training-config"],
        "package": {"sha256": "catalog-owned", "signature": "catalog-owned", "sbom": "sbom.cdx.json"},
        "installHooks": install_hooks or [],
    }


def build_package(root: Path, *, version: str = "0.1.0", manifest: dict | None = None) -> Path:
    package = root / f"agent-{version}.zip"
    payload = manifest or manifest_dict(version=version)
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(payload))
        archive.writestr("bin/next-trainer-pi-sidecar.exe", b"mock executable")
        archive.writestr("ui/index.js", "export default {}")
        archive.writestr("sbom.cdx.json", '{"bomFormat":"CycloneDX"}')
        archive.writestr("LICENSE", "MIT")
    return package


def signed_entry(package: Path, key: bytes, *, version: str = "0.1.0", **overrides) -> MarketplaceEntry:
    data = {
        "id": "next-trainer-pi-agent",
        "name": "Next Trainer Pi Agent",
        "publisher_id": "approved-publisher-id",
        "description": "Optional agent",
        "latest_version": version,
        "channel": "stable",
        "host_compatibility": ">=2.9.2 <3.0.0",
        "platforms": ["win32-x64"],
        "package_size": package.stat().st_size,
        "permissions_summary": ["model-provider", "training-config"],
        "license": "MIT",
        "package_url": package.as_uri(),
        "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "signing_key_id": "test-key",
        "published_at": "2026-08-21T00:00:00Z",
        "signature": "",
    }
    data.update(overrides)
    entry = MarketplaceEntry.model_validate(data)
    data["signature"] = hmac.new(key, canonical_entry_payload(entry), hashlib.sha256).hexdigest()
    return MarketplaceEntry.model_validate(data)


def manager_for(root: Path, *, health=None) -> tuple[MarketplaceManager, bytes]:
    key = b"stage-1-mock-signing-key"
    paths = MarketplacePaths(root)
    return (
        MarketplaceManager(
            paths=paths,
            store=MarketplaceStore(paths.registry_file),
            trust=TrustStore({"test-key": ("approved-publisher-id", key)}),
            host_version=HOST_VERSION,
            platform="win32-x64",
            health_check=health,
        ),
        key,
    )


def test_manifest_rejects_unknown_fields_and_arbitrary_install_hooks():
    valid = manifest_dict()
    assert PluginManifest.model_validate(valid).id == "next-trainer-pi-agent"

    with pytest.raises(ValidationError):
        PluginManifest.model_validate({**valid, "unexpected": True})

    with pytest.raises(ValidationError):
        PluginManifest.model_validate(manifest_dict(install_hooks=["powershell -File install.ps1"]))


@pytest.mark.parametrize("unsafe", ["../agent", "agent/child", "C:agent", "agent\\child", ""])
def test_paths_reject_unsafe_identifiers(unsafe: str):
    with tempfile.TemporaryDirectory() as td:
        paths = MarketplacePaths(Path(td))
        with pytest.raises(PathPolicyError):
            paths.plugin_versions(unsafe)


def test_store_writes_atomically_and_recovers_invalid_json():
    with tempfile.TemporaryDirectory() as td:
        registry = Path(td) / "registry.json"
        store = MarketplaceStore(registry)
        store.set_plugin("next-trainer-pi-agent", {"active_version": "0.1.0", "enabled": False})
        assert json.loads(registry.read_text(encoding="utf-8"))["plugins"]["next-trainer-pi-agent"]["active_version"] == "0.1.0"
        assert not registry.with_suffix(".json.tmp").exists()

        registry.write_text("{broken", encoding="utf-8")
        with pytest.raises(ValueError, match="invalid marketplace registry"):
            MarketplaceStore(registry).snapshot()


def test_trust_rejects_hash_signature_unknown_and_revoked_key():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        package = build_package(root)
        key = b"trusted"
        entry = signed_entry(package, key)
        trust = TrustStore({"test-key": ("approved-publisher-id", key)})
        trust.verify(entry, package)

        package.write_bytes(package.read_bytes() + b"tamper")
        with pytest.raises(TrustError, match="size|sha256"):
            trust.verify(entry, package)

        fresh = build_package(root)
        entry = signed_entry(fresh, key)
        with pytest.raises(TrustError, match="unknown signing key"):
            TrustStore({}).verify(entry, fresh)
        with pytest.raises(TrustError, match="revoked"):
            TrustStore({"test-key": ("approved-publisher-id", key)}, revoked_keys={"test-key"}).verify(entry, fresh)


def test_install_enable_disable_update_rollback_and_uninstall_preserves_user_data():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manager, key = manager_for(root)

        package_v1 = build_package(root, version="0.1.0")
        status = manager.install(signed_entry(package_v1, key, version="0.1.0"), package_v1)
        assert status.active_version == "0.1.0"
        assert status.enabled is False
        assert manager.paths.version_dir(status.id, "0.1.0").is_dir()

        assert manager.enable(status.id).enabled is True
        assert manager.disable(status.id).enabled is False

        package_v2 = build_package(root, version="0.2.0")
        updated = manager.install(signed_entry(package_v2, key, version="0.2.0"), package_v2)
        assert updated.active_version == "0.2.0"
        assert updated.previous_version == "0.1.0"
        rolled_back = manager.rollback(updated.id)
        assert rolled_back.active_version == "0.1.0"

        data_dir = manager.paths.user_data_dir(updated.id)
        data_dir.mkdir(parents=True)
        (data_dir / "auth.json").write_text("{}", encoding="utf-8")
        removed = manager.uninstall(updated.id)
        assert removed.state == "not_installed"
        assert data_dir.is_dir()
        assert not manager.paths.plugin_root(updated.id).exists()


def test_failed_update_health_keeps_old_active_version_and_cleans_staging():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        def health(manifest: PluginManifest, _directory: Path) -> bool:
            return manifest.version != "0.2.0"

        manager, key = manager_for(root, health=health)
        package_v1 = build_package(root, version="0.1.0")
        manager.install(signed_entry(package_v1, key, version="0.1.0"), package_v1)

        package_v2 = build_package(root, version="0.2.0")
        with pytest.raises(RuntimeError, match="health check failed"):
            manager.install(signed_entry(package_v2, key, version="0.2.0"), package_v2)

        status = manager.status("next-trainer-pi-agent")
        assert status.active_version == "0.1.0"
        assert not manager.paths.version_dir(status.id, "0.2.0").exists()
        assert list(manager.paths.staging_root.glob("*")) == []


def test_verified_update_preserves_explicit_enabled_state():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manager, key = manager_for(root)
        package_v1 = build_package(root, version="0.1.0")
        manager.install(signed_entry(package_v1, key, version="0.1.0"), package_v1)
        manager.enable("next-trainer-pi-agent")

        package_v2 = build_package(root, version="0.2.0")
        status = manager.install(signed_entry(package_v2, key, version="0.2.0"), package_v2)

        assert status.active_version == "0.2.0"
        assert status.enabled is True
        assert status.state == "enabled"


def test_archive_rejects_path_traversal_and_file_count_limit():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manager, key = manager_for(root)
        malicious = root / "malicious.zip"
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("../escape.txt", "no")
            archive.writestr("plugin.json", json.dumps(manifest_dict()))
        entry = signed_entry(malicious, key)
        with pytest.raises(PackageValidationError, match="unsafe archive path"):
            manager.install(entry, malicious)

        crowded = root / "crowded.zip"
        with zipfile.ZipFile(crowded, "w") as archive:
            archive.writestr("plugin.json", json.dumps(manifest_dict()))
            archive.writestr("one", "1")
            archive.writestr("two", "2")
        entry = signed_entry(crowded, key)
        manager.package_limits = PackageLimits(max_files=2)
        with pytest.raises(PackageValidationError, match="file count"):
            manager.install(entry, crowded)


def test_manifest_entry_identity_compatibility_platform_and_permissions_must_match():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manager, key = manager_for(root)

        package = build_package(root, manifest=manifest_dict(version="9.9.9"))
        with pytest.raises(PackageValidationError, match="version does not match"):
            manager.install(signed_entry(package, key, version="0.1.0"), package)

        package = build_package(root)
        entry = signed_entry(package, key, host_compatibility=">=3.0.0", platforms=["linux-x64"])
        with pytest.raises(TrustError, match="host compatibility"):
            manager.install(entry, package)

        entry = signed_entry(package, key, permissions_summary=["shell"])
        with pytest.raises(PackageValidationError, match="permissions"):
            manager.install(entry, package)

        shell_manifest = manifest_dict()
        shell_manifest["permissions"] = ["shell"]
        with pytest.raises(ValidationError, match="permission"):
            PluginManifest.model_validate(shell_manifest)

from __future__ import annotations

from datetime import datetime
import ipaddress
import json
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, root_validator, validator


_PYDANTIC_V2 = hasattr(BaseModel, "model_validate")


ALLOWED_PLUGIN_PERMISSIONS = frozenset(
    {
        "model-provider",
        "training-config",
        "dataset-review",
        "caption-commit",
        "metrics-read",
        "artifacts-read",
        "external-civitai-read",
    }
)


class StrictModel(BaseModel):
    """Pydantic 1/2 bridge; the application runtime is still on Pydantic 1."""

    class Config:
        extra = "forbid"
        allow_population_by_field_name = True

    if not _PYDANTIC_V2:
        @classmethod
        def model_validate(cls, value):
            return cls.parse_obj(value)

        @classmethod
        def model_validate_json(cls, value):
            return cls.parse_raw(value)

        def model_dump(self, *, mode="python", by_alias=False, exclude=None, **_kwargs):
            if mode == "json":
                return json.loads(self.json(by_alias=by_alias, exclude=exclude))
            return self.dict(by_alias=by_alias, exclude=exclude)


class MarketplaceEntry(StrictModel):
    id: str
    name: str
    publisher_id: str
    description: str = ""
    icon: str | None = None
    latest_version: str
    channel: Literal["stable", "beta"] = "stable"
    host_compatibility: str
    platforms: list[str]
    package_size: int = Field(gt=0)
    permissions_summary: list[str]
    license: str
    release_notes_url: str | None = None
    package_url: str
    sha256: str
    signature: str
    signing_key_id: str
    published_at: datetime

    @validator("sha256")
    def validate_sha256(cls, value: str) -> str:
        if not re.fullmatch(r"[a-fA-F0-9]{64}", value):
            raise ValueError("sha256 must contain exactly 64 hexadecimal characters")
        return value

    @validator("signature")
    def validate_signature(cls, value: str) -> str:
        if value and not re.fullmatch(r"[a-fA-F0-9]{64}", value):
            raise ValueError("signature must contain exactly 64 hexadecimal characters")
        return value

    @validator("package_url")
    def validate_package_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("package_url must be an HTTPS URL without credentials or fragment")
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("package_url cannot target a non-public IP address")
        return value

    @validator("permissions_summary")
    def validate_permissions_summary(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - ALLOWED_PLUGIN_PERMISSIONS)
        if unknown:
            raise ValueError("catalog entry contains unregistered plugin permissions")
        if len(value) != len(set(value)):
            raise ValueError("catalog entry contains duplicate plugin permissions")
        return value

    @validator("platforms")
    def validate_platforms(cls, value: list[str]) -> list[str]:
        if not value or len(value) != len(set(value)) or any(not item for item in value):
            raise ValueError("catalog entry platforms must be unique and non-empty")
        return value


class MarketplaceCatalog(StrictModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    publisher_id: str = Field(alias="publisherId")
    signing_key_id: str = Field(alias="signingKeyId")
    generated_at: datetime = Field(alias="generatedAt")
    entries: list[MarketplaceEntry]
    signature: str

    @validator("signature")
    def validate_catalog_signature(cls, value: str) -> str:
        if value and not re.fullmatch(r"[a-fA-F0-9]{64}", value):
            raise ValueError("catalog signature must contain exactly 64 hexadecimal characters")
        return value

    @validator("entries")
    def validate_catalog_entries(cls, value: list[MarketplaceEntry]) -> list[MarketplaceEntry]:
        identities = [entry.id for entry in value]
        if len(identities) != len(set(identities)):
            raise ValueError("catalog entries must have unique plugin identities")
        if len(value) > 10_000:
            raise ValueError("catalog entry count limit exceeded")
        return value


class RuntimeDeclaration(StrictModel):
    kind: Literal["executable"]
    entrypoint: str
    build_node: str | None = Field(default=None, alias="buildNode")
    embedded_runtime: str | None = Field(default=None, alias="embeddedRuntime")


class UIExtensionDeclaration(StrictModel):
    entrypoint: str
    settings_entrypoint: str | None = Field(default=None, alias="settingsEntrypoint")
    extension_api: str = Field(alias="extensionApi")
    placements: list[Literal["floating-panel", "artifact-detail"]]


class PackageDeclaration(StrictModel):
    sha256: str
    signature: str
    sbom: str


class BridgeMethodDeclaration(StrictModel):
    method: str
    permission: str
    params_schema: dict = Field(alias="paramsSchema")

    @validator("method")
    def validate_method(cls, value: str) -> str:
        if len(value) > 128 or not re.fullmatch(r"[a-z][a-z0-9-]*(?:\.[A-Za-z][A-Za-z0-9-]*)+", value):
            raise ValueError("bridge method must be a namespaced identifier")
        return value

    @validator("permission")
    def validate_permission(cls, value: str) -> str:
        if value not in ALLOWED_PLUGIN_PERMISSIONS:
            raise ValueError("bridge method requires a registered plugin permission")
        return value

    @validator("params_schema")
    def validate_params_schema(cls, value: dict) -> dict:
        from mikazuki.plugin_host.schema import validate_json_object_schema

        return validate_json_object_schema(value)


class BridgeDeclaration(StrictModel):
    requests: list[BridgeMethodDeclaration] = Field(default_factory=list)
    streams: list[BridgeMethodDeclaration] = Field(default_factory=list)

    @root_validator
    def methods_must_be_unique(cls, values):
        methods = [item.method for item in (values.get("requests") or []) + (values.get("streams") or [])]
        if len(methods) != len(set(methods)):
            raise ValueError("bridge methods must be unique across request and stream declarations")
        return values


class PluginManifest(StrictModel):
    id: str
    publisher: str
    version: str
    protocol_version: str = Field(alias="protocolVersion")
    host_compatibility: str = Field(alias="hostCompatibility")
    platforms: list[str]
    runtime: RuntimeDeclaration
    ui: UIExtensionDeclaration
    bridge: BridgeDeclaration = Field(default_factory=BridgeDeclaration)
    capabilities: list[str]
    permissions: list[str]
    package: PackageDeclaration
    install_hooks: list[str] = Field(default_factory=list, alias="installHooks")

    @validator("install_hooks")
    def reject_install_hooks(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("arbitrary install hooks are forbidden")
        return value

    @validator("permissions")
    def reject_unregistered_permissions(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - ALLOWED_PLUGIN_PERMISSIONS)
        if unknown:
            raise ValueError(f"unregistered plugin permission(s): {', '.join(unknown)}")
        if len(value) != len(set(value)):
            raise ValueError("duplicate plugin permissions are forbidden")
        return value

    @root_validator
    def bridge_permissions_must_be_declared(cls, values):
        declared = set(values.get("permissions") or ())
        bridge = values.get("bridge")
        if bridge is not None:
            required = {item.permission for item in bridge.requests + bridge.streams}
            if not required <= declared:
                raise ValueError("bridge method permission is not declared by the plugin")
        return values


class PluginStatus(StrictModel):
    id: str
    state: Literal["not_installed", "installed", "enabled", "runtime_error", "broken"]
    active_version: str | None = None
    previous_version: str | None = None
    enabled: bool = False
    installed_versions: list[str] = Field(default_factory=list)
    reason: str = ""
    runtime_state: Literal["stopped", "starting", "running", "crashed"] | None = None
    runtime_pid: int | None = None
    granted_permissions: list[str] = Field(default_factory=list)

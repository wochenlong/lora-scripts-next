from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Literal

from pydantic import BaseModel, Field, validator


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


class RuntimeDeclaration(StrictModel):
    kind: Literal["executable"]
    entrypoint: str
    build_node: str | None = Field(default=None, alias="buildNode")
    embedded_runtime: str | None = Field(default=None, alias="embeddedRuntime")


class UIExtensionDeclaration(StrictModel):
    entrypoint: str
    extension_api: str = Field(alias="extensionApi")
    placements: list[Literal["floating-panel", "artifact-detail"]]


class PackageDeclaration(StrictModel):
    sha256: str
    signature: str
    sbom: str


class PluginManifest(StrictModel):
    id: str
    publisher: str
    version: str
    protocol_version: str = Field(alias="protocolVersion")
    host_compatibility: str = Field(alias="hostCompatibility")
    platforms: list[str]
    runtime: RuntimeDeclaration
    ui: UIExtensionDeclaration
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


class PluginStatus(StrictModel):
    id: str
    state: Literal["not_installed", "installed", "enabled", "broken"]
    active_version: str | None = None
    previous_version: str | None = None
    enabled: bool = False
    installed_versions: list[str] = Field(default_factory=list)
    reason: str = ""

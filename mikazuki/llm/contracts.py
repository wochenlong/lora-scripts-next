from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

LLMCapability = Literal["text", "vision"]
LLMSource = Literal["remote", "local-endpoint", "managed-local"]


class LLMContractError(ValueError):
    """Invalid shared LLM configuration or request contract."""


class LLMRouteError(RuntimeError):
    """No profile can satisfy a requested capability."""

    def __init__(self, message: str, code: str = "llm_not_ready"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LLMProfile:
    id: str
    name: str
    endpoint: str
    model: str
    source: LLMSource
    capabilities: tuple[LLMCapability, ...] = ("text",)
    languages: tuple[str, ...] = ("en",)
    api_key: str = ""
    asset_id: str | None = None
    revision: str | None = None
    enabled: bool = True
    ready: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def is_remote(self) -> bool:
        return self.source == "remote"

    @property
    def supports_vision(self) -> bool:
        return "vision" in self.capabilities

    def supports(self, capability: LLMCapability, language: str | None = None) -> bool:
        if not self.enabled or not self.ready or capability not in self.capabilities:
            return False
        return language is None or language in self.languages or "*" in self.languages

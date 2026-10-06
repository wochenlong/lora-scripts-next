from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .client import build_chat_payload, encode_image_data_url
from .config import UnifiedConfigStore, config_revision
from .contracts import LLMCapability, LLMContractError, LLMProfile
from .http import chat_completion
from .routing import choose_profile


def profile_from_dict(item: dict[str, Any]) -> LLMProfile:
    return LLMProfile(
        id=str(item["id"]),
        name=str(item.get("name") or item["id"]),
        endpoint=str(item["endpoint"]),
        model=str(item["model"]),
        source=str(item.get("source") or "remote"),
        capabilities=tuple(item.get("capabilities") or ("text",)),
        languages=tuple(item.get("languages") or ("en",)),
        api_key=str(item.get("api_key") or ""),
        asset_id=item.get("asset_id"),
        revision=item.get("revision"),
        enabled=bool(item.get("enabled", True)),
        ready=bool(item.get("ready", True)),
        metadata=item.get("metadata") or {},
    )


class UnifiedLLMService:
    def __init__(self, config_store: UnifiedConfigStore, *, session_factory=None):
        self.config_store = config_store
        self.session_factory = session_factory

    def config(self, *, masked: bool = True) -> dict[str, Any]:
        return self.config_store.load_masked() if masked else self.config_store.load()

    def profiles(self, *, masked: bool = True) -> list[dict[str, Any]]:
        return list(self.config(masked=masked).get("profiles", []))

    def save_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.config_store.save(payload)

    def resolve(
        self,
        capability: LLMCapability,
        *,
        language: str | None = None,
        profile_id: str | None = None,
        allow_local_fallback: bool = True,
    ) -> LLMProfile:
        config = self.config_store.load()
        return choose_profile(
            config.get("profiles", []),
            capability,
            language=language,
            preferred_id=profile_id,
            allow_local_fallback=allow_local_fallback,
        )

    def revision(self, profile_id: str | None = None, *, prompt_revision: str | None = None) -> str:
        profile = self.resolve("text", profile_id=profile_id, allow_local_fallback=True)
        return config_revision(profile, prompt_revision)

    async def complete_text(
        self,
        prompt: str,
        *,
        language: str | None = None,
        profile_id: str | None = None,
        response_schema: dict[str, Any] | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
        allow_local_fallback: bool = True,
    ) -> tuple[LLMProfile, dict[str, Any], str]:
        profile = self.resolve(
            "text",
            language=language,
            profile_id=profile_id,
            allow_local_fallback=allow_local_fallback,
        )
        payload = build_chat_payload(
            profile,
            prompt=prompt,
            response_schema=response_schema,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        kwargs = {}
        if self.session_factory is not None:
            kwargs["session_factory"] = self.session_factory
        try:
            envelope, content = await chat_completion(profile, payload, **kwargs)
            return profile, envelope, content
        except Exception:
            if not profile.is_remote or not allow_local_fallback:
                raise
            fallback = self._local_fallback("text", language)
            payload = build_chat_payload(fallback, prompt=prompt, response_schema=response_schema, max_tokens=max_tokens, temperature=temperature)
            envelope, content = await chat_completion(fallback, payload, **kwargs)
            return fallback, envelope, content

    async def complete_vision(
        self,
        image_path: str | Path,
        prompt: str,
        *,
        language: str | None = None,
        profile_id: str | None = None,
        response_schema: dict[str, Any] | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
        allow_local_fallback: bool = True,
    ) -> tuple[LLMProfile, dict[str, Any], str, dict[str, Any]]:
        profile = self.resolve(
            "vision",
            language=language,
            profile_id=profile_id,
            allow_local_fallback=allow_local_fallback,
        )
        image_data_url, image_info = encode_image_data_url(image_path)
        payload = build_chat_payload(
            profile,
            prompt=prompt,
            image_data_url=image_data_url,
            response_schema=response_schema,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        kwargs = {}
        if self.session_factory is not None:
            kwargs["session_factory"] = self.session_factory
        try:
            envelope, content = await chat_completion(profile, payload, **kwargs)
            return profile, envelope, content, image_info
        except Exception:
            if not profile.is_remote or not allow_local_fallback:
                raise
            fallback = self._local_fallback("vision", language)
            payload = build_chat_payload(
                fallback,
                prompt=prompt,
                image_data_url=image_data_url,
                response_schema=response_schema,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            envelope, content = await chat_completion(fallback, payload, **kwargs)
            return fallback, envelope, content, image_info

    def _local_fallback(self, capability: LLMCapability, language: str | None) -> LLMProfile:
        profiles = [
            item for item in self.config_store.load().get("profiles", [])
            if item.get("source") != "remote"
        ]
        return choose_profile(profiles, capability, language=language, allow_local_fallback=True)

    async def connection_test(
        self,
        *,
        capability: LLMCapability = "text",
        profile_id: str | None = None,
        image_path: str | Path | None = None,
        prompt: str = 'Reply with JSON: {"ok": true}.',
        language: str | None = None,
    ) -> dict[str, Any]:
        if capability == "vision":
            if image_path is None:
                raise LLMContractError("vision connection test requires an image")
            profile, envelope, content, image_info = await self.complete_vision(
                image_path,
                prompt,
                language=language,
                profile_id=profile_id,
                response_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False},
            )
            return {
                "profile_id": profile.id,
                "profile_revision": config_revision(profile),
                "capability": capability,
                "content": content,
                "image": image_info,
                "finish_reason": envelope.get("choices", [{}])[0].get("finish_reason"),
            }
        profile, envelope, content = await self.complete_text(
            prompt,
            language=language,
            profile_id=profile_id,
            response_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False},
        )
        return {
            "profile_id": profile.id,
            "profile_revision": config_revision(profile),
            "capability": capability,
            "content": content,
            "finish_reason": envelope.get("choices", [{}])[0].get("finish_reason"),
        }

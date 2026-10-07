from __future__ import annotations

from pathlib import Path
import copy
from typing import Any, Callable

from .client import build_chat_payload, encode_image_data_url, parse_json_content
from .config import UnifiedConfigStore, config_revision, mask_profiles
from .contracts import LLMCapability, LLMContractError, LLMProfile
from .http import LLMRequestError, chat_completion
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
        metadata={**(item.get("metadata") or {}), "secret_revision": item.get("secret_revision", 0)},
    )


class UnifiedLLMService:
    def __init__(self, config_store: UnifiedConfigStore, *, session_factory=None, config_snapshot=None):
        self.config_store = config_store
        self.session_factory = session_factory
        self.config_snapshot = copy.deepcopy(config_snapshot)

    def config(self, *, masked: bool = True) -> dict[str, Any]:
        if self.config_snapshot is not None:
            config = copy.deepcopy(self.config_snapshot)
            if masked:
                config = mask_profiles(config)
        else:
            config = self.config_store.load_masked() if masked else self.config_store.load()
        for profile in config["profiles"]:
            if profile.get("asset_id") == "qwen3-vl-2b-local":
                from .runtime import get_local_vision_service, llm_config_store
                if self.config_store.path == llm_config_store.path:
                    profile["ready"] = get_local_vision_service().status()["state"] == "running"
            if profile.get("asset_id") == "qwen3.5-0.8b-local":
                from .runtime import llm_config_store
                if self.config_store.path == llm_config_store.path:
                    from mikazuki.tag_translation.runtime import local_model_service
                    profile["ready"] = local_model_service.status()["state"] == "running"
        return config

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
        allow_local_fallback: bool = False,
    ) -> LLMProfile:
        config = self.config(masked=False)
        if profile_id:
            selected = next((item for item in config.get("profiles", []) if item["id"] == profile_id), None)
            if selected is None:
                from .contracts import LLMRouteError
                raise LLMRouteError("selected profile does not exist", "llm_profile_not_found")
            if capability not in selected["capabilities"]:
                from .contracts import LLMRouteError
                raise LLMRouteError("selected profile does not have required capability", "llm_capability_vision_required" if capability == "vision" else "llm_capability_text_required")
        return choose_profile(
            config.get("profiles", []),
            capability,
            language=language,
            preferred_id=profile_id or config.get("routes", {}).get("caption" if capability == "vision" else "translation"),
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
        allow_local_fallback: bool = False,
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
        except (LLMRequestError, LLMContractError):
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
        system_prompt: str = "",
        language: str | None = None,
        profile_id: str | None = None,
        response_schema: dict[str, Any] | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
        allow_local_fallback: bool = False,
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
            system_prompt=system_prompt,
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
        except (LLMRequestError, LLMContractError):
            if not profile.is_remote or not allow_local_fallback:
                raise
            fallback = self._local_fallback("vision", language)
            payload = build_chat_payload(
                fallback,
                prompt=prompt,
                system_prompt=system_prompt,
                image_data_url=image_data_url,
                response_schema=response_schema,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            envelope, content = await chat_completion(fallback, payload, **kwargs)
            return fallback, envelope, content, image_info

    def _local_fallback(self, capability: LLMCapability, language: str | None) -> LLMProfile:
        profiles = [
            item for item in self.config(masked=False).get("profiles", [])
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
        # Connection tests diagnose exactly the selected endpoint. Production
        # requests keep remote-first routing, but diagnostics never reroute.
        if profile_id:
            selected = next((item for item in self.profiles(masked=False) if item["id"] == profile_id), None)
            if selected is None:
                from .contracts import LLMRouteError
                raise LLMRouteError("selected profile does not exist", "llm_profile_not_found")
            profile = profile_from_dict(selected)
            if not profile.supports(capability, language):
                from .contracts import LLMRouteError
                raise LLMRouteError("selected profile is not ready for the requested capability or language")
        else:
            profile = self.resolve(capability, language=language, allow_local_fallback=False)
        image_info = None
        image_data_url = None
        if capability == "vision":
            if image_path is None:
                raise LLMContractError("vision connection test requires an image")
            image_data_url, image_info = encode_image_data_url(image_path)
        payload = build_chat_payload(
            profile, prompt=prompt, image_data_url=image_data_url, max_tokens=64,
            response_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False},
        )
        kwargs = {"session_factory": self.session_factory} if self.session_factory is not None else {}
        envelope, content = await chat_completion(profile, payload, **kwargs)
        finish_reason = envelope.get("choices", [{}])[0].get("finish_reason")
        parsed = parse_json_content(content)
        if finish_reason == "length" or set(parsed) != {"ok"} or parsed["ok"] is not True:
            raise LLMContractError("connection test response must be exactly an affirmative JSON result")
        result = {
            "profile_id": profile.id,
            "profile_revision": config_revision(profile),
            "capability": capability,
            "ok": True,
            "finish_reason": finish_reason,
        }
        if image_info is not None:
            result["image"] = image_info
        return result

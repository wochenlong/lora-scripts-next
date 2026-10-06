from __future__ import annotations

from collections.abc import Iterable, Mapping

from .contracts import LLMCapability, LLMProfile, LLMRouteError


def _as_profile(item: LLMProfile | Mapping[str, object]) -> LLMProfile:
    if isinstance(item, LLMProfile):
        return item
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


def choose_profile(
    profiles: Iterable[LLMProfile | Mapping[str, object]],
    capability: LLMCapability,
    *,
    language: str | None = None,
    preferred_id: str | None = None,
    allow_local_fallback: bool = False,
) -> LLMProfile:
    """Choose remote first, then an explicitly allowed local fallback."""
    candidates = [_as_profile(item) for item in profiles]
    ready = [item for item in candidates if item.supports(capability, language)]
    if preferred_id:
        preferred = [item for item in ready if item.id == preferred_id]
        if preferred and preferred[0].is_remote:
            return preferred[0]
    remote = [item for item in ready if item.is_remote]
    if remote:
        return remote[0]
    if allow_local_fallback:
        if preferred_id:
            preferred = [item for item in ready if item.id == preferred_id]
            if preferred:
                return preferred[0]
        local = [item for item in ready if not item.is_remote]
        if local:
            return local[0]
    code = "llm_capability_vision_required" if capability == "vision" else "llm_not_ready"
    raise LLMRouteError(f"No ready {capability} profile is available", code)

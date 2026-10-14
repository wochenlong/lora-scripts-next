from __future__ import annotations

from collections.abc import Iterable, Mapping

from .contracts import LLMCapability, LLMProfile, LLMRouteError


def _as_profile(item: LLMProfile | Mapping[str, object]) -> LLMProfile:
    if isinstance(item, LLMProfile):
        return item
    from .config import profile_ready
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
        ready=bool(item.get("ready", False)) and profile_ready(dict(item)) if "verified_capabilities" in item else bool(item.get("ready", True)),
        metadata={**(item.get("metadata") or {}), "secret_revision": item.get("secret_revision", 0)},
        verified_capabilities=tuple(item.get("verified_capabilities", [])) if "verified_capabilities" in item else None,
    )


def candidate_profiles(
    profiles: Iterable[LLMProfile | Mapping[str, object]],
    capability: LLMCapability,
    *,
    language: str | None = None,
    preferred_id: str | None = None,
    allow_local_fallback: bool = False,
) -> list[LLMProfile]:
    """All ready remotes precede explicitly enabled local candidates."""
    candidates = [_as_profile(item) for item in profiles]
    ready = [item for item in candidates if item.supports(capability, language)]
    remote = [item for item in ready if item.is_remote]
    remote.sort(key=lambda item: item.id != preferred_id)
    selected = list(remote)
    if allow_local_fallback:
        local = [item for item in ready if not item.is_remote]
        local.sort(key=lambda item: item.id != preferred_id)
        selected.extend(local)
    if selected:
        return selected
    code = "llm_capability_vision_required" if capability == "vision" else "llm_not_ready"
    raise LLMRouteError(f"No ready {capability} profile is available", code)


def choose_profile(profiles, capability, *, language=None, preferred_id=None, allow_local_fallback=False) -> LLMProfile:
    return candidate_profiles(profiles, capability, language=language, preferred_id=preferred_id,
                              allow_local_fallback=allow_local_fallback)[0]

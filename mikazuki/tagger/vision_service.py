from __future__ import annotations

from pathlib import Path

from mikazuki.llm.client import build_chat_payload, encode_image_data_url
from mikazuki.llm.contracts import LLMProfile
from mikazuki.llm.http import chat_completion
from .caption import CAPTION_SCHEMA, CaptionResult, parse_caption_response, render_prompt, require_vision_profile


def _coerce_profile(profile: LLMProfile | dict) -> LLMProfile:
    if isinstance(profile, LLMProfile):
        return profile
    return LLMProfile(
        id=str(profile["id"]),
        name=str(profile.get("name") or profile["id"]),
        endpoint=str(profile["endpoint"]),
        model=str(profile["model"]),
        source=str(profile.get("source") or "remote"),
        capabilities=tuple(profile.get("capabilities") or ("text",)),
        languages=tuple(profile.get("languages") or ("en",)),
        api_key=str(profile.get("api_key") or ""),
        asset_id=profile.get("asset_id"),
        revision=profile.get("revision"),
        enabled=bool(profile.get("enabled", True)),
        ready=bool(profile.get("ready", True)),
        metadata=profile.get("metadata") or {},
    )


class VisionCaptionService:
    def __init__(self, *, session_factory=None):
        self.session_factory = session_factory

    async def caption(
        self,
        profile: LLMProfile,
        image_path: str | Path,
        *,
        prompt_template: str,
        language: str,
        mode: str = "natural",
        image_name: str = "",
        existing_caption: str = "",
        existing_tags: str = "",
    ) -> CaptionResult:
        profile = _coerce_profile(profile)
        require_vision_profile(profile)
        prompt, _snapshot = render_prompt(
            prompt_template,
            language=language,
            mode=mode,
            image_name=image_name,
            existing_caption=existing_caption,
            existing_tags=existing_tags,
        )
        image_data_url, _image_info = encode_image_data_url(image_path)
        payload = build_chat_payload(
            profile,
            prompt=prompt,
            image_data_url=image_data_url,
            response_schema=CAPTION_SCHEMA,
            max_tokens=512,
            temperature=0,
        )
        kwargs = {}
        if self.session_factory is not None:
            kwargs["session_factory"] = self.session_factory
        _envelope, content = await chat_completion(profile, payload, **kwargs)
        return parse_caption_response(content, language=language)

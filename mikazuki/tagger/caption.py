from __future__ import annotations

import json
from dataclasses import dataclass

from mikazuki.llm.client import parse_json_content
from mikazuki.llm.contracts import LLMContractError, LLMProfile

CAPTION_LAYOUTS = {"tags_then_caption", "caption_then_tags", "tags_only", "caption_only"}
CAPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "caption": {"type": "string", "minLength": 1, "maxLength": 2000},
        "language": {"type": "string"},
    },
    "required": ["caption", "language"],
    "additionalProperties": False,
}


class CaptionContractError(LLMContractError):
    pass


@dataclass(frozen=True)
class CaptionResult:
    caption: str
    language: str


def render_prompt(template: str, *, language: str, mode: str, image_name: str = "",
                  existing_caption: str = "", existing_tags: str = "") -> tuple[str, str]:
    if not isinstance(template, str) or not template.strip():
        raise CaptionContractError("prompt template cannot be empty")
    if len(template) > 8000:
        raise CaptionContractError("prompt template is too long")
    values = {
        "language": language,
        "mode": mode,
        "image_name": image_name[:255],
        "existing_caption": existing_caption[:4000],
        "existing_tags": existing_tags[:2000],
    }
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered.strip(), json.dumps(values, ensure_ascii=False, sort_keys=True)


def parse_caption_response(content: str, *, language: str) -> CaptionResult:
    payload = parse_json_content(content)
    if set(payload) != {"caption", "language"}:
        raise CaptionContractError("caption response must contain exactly caption and language")
    caption = payload["caption"]
    if not isinstance(caption, str) or not caption.strip():
        raise CaptionContractError("caption must be non-empty text")
    if len(caption) > 2000 or chr(0) in caption or chr(96) * 3 in caption:
        raise CaptionContractError("caption contains invalid content")
    if payload["language"] != language:
        raise CaptionContractError("caption language does not match request")
    return CaptionResult(caption=caption.strip(), language=language)


def compose_caption(tags: list[str], caption: str, layout: str = "tags_then_caption") -> str:
    if layout not in CAPTION_LAYOUTS:
        raise CaptionContractError("unknown caption layout")
    clean_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
    clean_caption = str(caption or "").strip()
    tag_line = ", ".join(dict.fromkeys(clean_tags))
    if layout == "tags_only":
        return tag_line
    if layout == "caption_only":
        return clean_caption
    if not tag_line or not clean_caption:
        return tag_line or clean_caption
    if layout == "tags_then_caption":
        return tag_line + "\n\n" + clean_caption
    return clean_caption + "\n\n" + tag_line


def require_vision_profile(profile: LLMProfile | dict) -> None:
    supports_vision = (
        profile.supports_vision
        if isinstance(profile, LLMProfile)
        else "vision" in (profile.get("capabilities") or [])
    )
    if not supports_vision:
        raise CaptionContractError("caption profile must declare vision capability")

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from mikazuki.llm.client import parse_json_content
from mikazuki.llm.contracts import LLMContractError, LLMProfile

CAPTION_LAYOUTS = {"tags_then_caption", "caption_then_tags", "tags_only", "caption_only"}
DEFAULT_CAPTION_PROMPT = 'Describe the main visible content of the image in {{language}} (en means English). Return only a JSON object with exactly caption and language; language must be "{{language}}". Do not output Markdown.'
CAPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "caption": {"type": "string", "minLength": 1, "maxLength": 2000},
        "language": {"type": "string", "enum": ["zh-CN", "zh-TW", "en", "ja"]},
    },
    "required": ["caption", "language"],
    "additionalProperties": False,
}


class CaptionContractError(LLMContractError):
    code = "llm_invalid_response"


@dataclass(frozen=True)
class CaptionResult:
    caption: str
    language: str


def snapshot_prompt(request: dict, config: dict | None = None) -> dict:
    import copy
    result = copy.deepcopy(request)
    preset_id = result.get("prompt_id")
    if preset_id and not result.get("_prompt_frozen"):
        preset = next((item for item in (config or {}).get("prompt_presets", []) if item.get("id") == preset_id), None)
        if preset is None:
            raise CaptionContractError("prompt preset does not exist")
        result.setdefault("prompt", preset["template"])
        result.setdefault("language", preset["language"])
        result.setdefault("max_caption_length", preset.get("max_length", 2000))
        result.setdefault("system_prompt", preset.get("system_prompt", ""))
        result["preset_revision"] = preset.get("revision")
    result.setdefault("prompt", DEFAULT_CAPTION_PROMPT)
    result.setdefault("language", "en")
    result.setdefault("mode", "natural")
    result.setdefault("max_caption_length", 2000)
    result.setdefault("system_prompt", "")
    if not isinstance(result["system_prompt"], str) or len(result["system_prompt"]) > 8000:
        raise CaptionContractError("system prompt must be bounded text")
    maximum = result["max_caption_length"]
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 2000:
        raise CaptionContractError("caption length limit must be an integer between 1 and 2000")
    render_prompt(result["prompt"], language=result["language"], mode=result["mode"], image_name="image")
    result["_prompt_frozen"] = True
    return result


def render_prompt(template: str, *, language: str, mode: str, image_name: str = "",
                  existing_caption: str = "", existing_tags: str = "") -> tuple[str, str]:
    if not isinstance(template, str) or not template.strip():
        raise CaptionContractError("prompt template cannot be empty")
    if len(template) > 8000:
        raise CaptionContractError("prompt template is too long")
    if language not in {"zh-CN", "zh-TW", "en", "ja"}:
        raise CaptionContractError("unsupported caption language")
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
    if re.search(r"\{\{[^{}]*\}\}", rendered):
        raise CaptionContractError("prompt contains an unknown variable")
    return rendered.strip(), json.dumps(values, ensure_ascii=False, sort_keys=True)


def parse_caption_response(content: str, *, language: str, max_length: int = 2000) -> CaptionResult:
    payload = parse_json_content(content)
    if set(payload) != {"caption", "language"}:
        raise CaptionContractError("caption response must contain exactly caption and language")
    caption = payload["caption"]
    if not isinstance(caption, str) or not caption.strip():
        raise CaptionContractError("caption must be non-empty text")
    if len(caption) > max_length or chr(0) in caption or chr(96) * 3 in caption:
        raise CaptionContractError("caption contains invalid content")
    if payload["language"] != language:
        raise CaptionContractError("caption language does not match request")
    if language.startswith("zh") and not any("\u3400" <= char <= "\u9fff" for char in caption):
        raise CaptionContractError("caption does not contain Chinese text")
    if language == "en" and (not re.search(r"[A-Za-z]", caption) or re.search(r"[\u3400-\u9fff\u3040-\u30ff]", caption)):
        raise CaptionContractError("caption does not contain English-only text")
    if language == "ja" and not any("\u3040" <= char <= "\u30ff" or "\u3400" <= char <= "\u9fff" for char in caption):
        raise CaptionContractError("caption does not contain Japanese text")
    if re.search(r"(?:[A-Za-z]:[\\/]|file://|/(?:home|Users|mnt|data)/)", caption):
        raise CaptionContractError("caption contains a local path")
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


def merge_tag_caption(existing: str, generated: str, action: str, *, existed: bool, format_hint=None) -> str:
    """Keep legacy Tag ordering/dedup without modifying natural sentences."""
    from mikazuki.dataset_editor import detect_caption_format
    if action in {"prepend", "append"} and existing.strip() and (format_hint or detect_caption_format(existing)) != "tag":
        raise CaptionContractError("Tag merge cannot modify natural or mixed caption")
    output = [existing.strip()] if existed else []
    if action == "copy" or (action == "ignore" and not existed):
        output = [generated]
    elif action == "prepend":
        output.insert(0, generated)
    else:
        output.append(generated)
    return ", ".join(dict.fromkeys(item.strip() for item in ",".join(output).split(",")))


def require_vision_profile(profile: LLMProfile | dict) -> None:
    supports_vision = (
        profile.supports_vision
        if isinstance(profile, LLMProfile)
        else "vision" in (profile.get("capabilities") or [])
    )
    if not supports_vision:
        raise CaptionContractError("caption profile must declare vision capability")

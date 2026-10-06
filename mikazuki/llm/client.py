from __future__ import annotations

import base64
import io
import json
from collections.abc import Mapping
from typing import Any

from PIL import Image, ImageOps

from .contracts import LLMContractError, LLMProfile


def encode_image_data_url(path, *, max_side: int = 1024, quality: int = 85) -> tuple[str, dict[str, Any]]:
    """Encode a local image without exposing its path to a provider."""
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((max_side, max_side))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=quality)
    except Exception as exc:
        raise LLMContractError(f"image could not be encoded: {type(exc).__name__}") from exc
    raw = output.getvalue()
    return (
        "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii"),
        {"width": image.width, "height": image.height, "bytes": len(raw)},
    )


def build_chat_payload(
    profile: LLMProfile | Mapping[str, Any],
    *,
    prompt: str,
    image_data_url: str | None = None,
    response_schema: dict[str, Any] | None = None,
    max_tokens: int = 512,
    temperature: float = 0.0,
    stream: bool = False,
) -> dict[str, Any]:
    profile_model = profile.model if isinstance(profile, LLMProfile) else str(profile["model"])
    content: Any = prompt
    if image_data_url is not None:
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
    payload: dict[str, Any] = {
        "model": profile_model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max(1, min(int(max_tokens), 8192)),
        "temperature": max(0.0, min(float(temperature), 2.0)),
        "stream": bool(stream),
    }
    if response_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "caption",
                "strict": True,
                "schema": response_schema,
            },
        }
    return payload


def extract_chat_content(response: Mapping[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMContractError("LLM response has no chat content") from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMContractError("LLM response content must be non-empty text")
    return content.strip()


def parse_json_content(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMContractError("LLM response is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise LLMContractError("LLM JSON response must be an object")
    return parsed

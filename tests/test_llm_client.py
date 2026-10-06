from __future__ import annotations

import json

import pytest
from PIL import Image

from mikazuki.llm.client import (
    build_chat_payload,
    encode_image_data_url,
    extract_chat_content,
    parse_json_content,
)
from mikazuki.llm.config import validate_profile
from mikazuki.llm.contracts import LLMContractError


def profile():
    return validate_profile(
        {
            "id": "vision",
            "name": "Vision",
            "endpoint": "https://api.example.com/v1/chat/completions",
            "model": "vision",
            "source": "remote",
            "capabilities": ["text", "vision"],
            "languages": ["zh-CN"],
        }
    )


def test_image_encoder_returns_data_url_without_path(tmp_path):
    path = tmp_path / "sample.png"
    Image.new("RGBA", (2000, 1000), (255, 0, 0, 128)).save(path)
    data_url, info = encode_image_data_url(path, max_side=512)
    assert data_url.startswith("data:image/jpeg;base64,")
    assert info["width"] == 512
    assert info["height"] == 256
    assert str(path) not in data_url


def test_vision_payload_uses_openai_content_parts_and_schema():
    schema = {
        "type": "object",
        "properties": {"caption": {"type": "string"}},
        "required": ["caption"],
    }
    payload = build_chat_payload(
        profile(),
        prompt="Describe the image.",
        image_data_url="data:image/jpeg;base64,abc",
        response_schema=schema,
    )
    assert payload["messages"][0]["content"][1]["type"] == "image_url"
    assert payload["response_format"]["json_schema"]["strict"] is True


def test_text_payload_does_not_add_image_part():
    payload = build_chat_payload(profile(), prompt="Translate this tag.")
    assert payload["messages"][0]["content"] == "Translate this tag."


def test_response_adapters_validate_shape():
    content = extract_chat_content({"choices": [{"message": {"content": '{"caption":"ok"}'}}]})
    assert parse_json_content(content)["caption"] == "ok"
    with pytest.raises(LLMContractError):
        extract_chat_content({"choices": []})
    with pytest.raises(LLMContractError):
        parse_json_content("[]")


@pytest.mark.parametrize("content", [
    '{"caption":"first","caption":"second"}',
    '{"nested":{"ok":true,"ok":false}}',
    '{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}',
])
def test_strict_json_rejects_duplicate_keys_and_non_finite_numbers(content):
    with pytest.raises(LLMContractError):
        parse_json_content(content)

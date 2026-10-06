from __future__ import annotations

import pytest

from mikazuki.llm.config import validate_profile
from mikazuki.tagger.caption import (
    CaptionContractError,
    compose_caption,
    parse_caption_response,
    render_prompt,
    require_vision_profile,
)


def vision_profile(capabilities=("text", "vision")):
    return validate_profile(
        {
            "id": "p",
            "name": "P",
            "endpoint": "https://api.example.com/v1/chat/completions",
            "model": "m",
            "source": "remote",
            "capabilities": list(capabilities),
            "languages": ["zh-CN"],
        }
    )


def test_prompt_render_is_bounded_and_keeps_a_snapshot():
    rendered, snapshot = render_prompt(
        "请用 {{language}} 描述 {{image_name}}，模式是 {{mode}}。",
        language="zh-CN",
        mode="natural",
        image_name="a.png",
    )
    assert "zh-CN" in rendered
    assert "a.png" in rendered
    assert '"mode": "natural"' in snapshot


def test_caption_response_requires_exact_schema_and_language():
    result = parse_caption_response(
        '{"caption":"一只猫。","language":"zh-CN"}',
        language="zh-CN",
    )
    assert result.caption == "一只猫。"
    with pytest.raises(CaptionContractError):
        parse_caption_response('{"caption":"cat","language":"en"}', language="zh-CN")
    with pytest.raises(CaptionContractError):
        parse_caption_response('{"caption":"x","language":"zh-CN","extra":1}', language="zh-CN")


def test_compose_layout_preserves_natural_caption():
    assert compose_caption(["1girl", "1girl", "solo"], "她站在窗边。") == "1girl, solo\n\n她站在窗边。"
    assert compose_caption(["1girl"], "她站在窗边。", "caption_then_tags") == "她站在窗边。\n\n1girl"
    assert compose_caption(["1girl"], "她站在窗边。", "tags_only") == "1girl"


def test_caption_requires_vision_capability():
    require_vision_profile(vision_profile())
    with pytest.raises(CaptionContractError, match="vision"):
        require_vision_profile(vision_profile(("text",)))

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


def test_english_caption_rejects_chinese_body_even_if_json_language_is_en():
    for caption in ("一只猫坐在窗边。", "A cat 坐在窗边", "12345"):
        import json
        with pytest.raises(CaptionContractError, match="English"):
            parse_caption_response(json.dumps({"caption": caption, "language": "en"}), language="en")
    assert parse_caption_response('{"caption":"A cat by a window.","language":"en"}', language="en").caption == "A cat by a window."


def test_old_chinese_body_cached_as_english_is_regenerated(tmp_path):
    import sqlite3
    from PIL import Image
    from mikazuki.llm.cache import CaptionCache
    from mikazuki.llm.contracts import LLMProfile
    from mikazuki.tagger.caption_job import CaptionJobManager
    class EnglishService:
        calls = 0
        profile = LLMProfile(id="local", name="local", model="vision", endpoint="http://localhost:9999/v1/chat/completions", source="local-endpoint", capabilities=("vision",), languages=("en",))
        def resolve(self, *_args, **_kwargs):
            return self.profile
        async def complete_vision(self, *_args, **_kwargs):
            self.calls += 1
            return self.profile, {"choices": [{"finish_reason": "stop"}]}, '{"caption":"A cat.","language":"en"}', {}
    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (8, 8)).save(images / "cat.png")
    cache = CaptionCache(tmp_path / "cache.db")
    service = EnglishService()
    manager = CaptionJobManager(service, cache=cache)
    for attempt in range(2):
        manager.start({"path": str(images), "allow_local_fallback": True})
        manager._thread.join(5)
        assert manager.status()["succeeded"] == 1
        assert (images / "cat.txt").read_text(encoding="utf-8").strip() == "A cat."
        if attempt == 0:
            with sqlite3.connect(cache.path) as connection:
                connection.execute("UPDATE caption_results SET caption='一只猫。'")
            (images / "cat.txt").unlink()
    assert service.calls == 2

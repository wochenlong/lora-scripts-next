from __future__ import annotations

import asyncio

from PIL import Image

from mikazuki.llm.config import validate_profile
from mikazuki.tagger.vision_service import VisionCaptionService


class FakeResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def text(self):
        return '{"choices":[{"message":{"content":"{\\"caption\\":\\"一只猫。\\",\\"language\\":\\"zh-CN\\"}"}}]}'

    async def json(self, **_kwargs):
        return {
            "choices": [
                {"message": {"content": '{"caption":"一只猫。","language":"zh-CN"}'}}
            ]
        }


class FakeSession:
    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def post(self, *_args, **_kwargs):
        return FakeResponse()


def fake_session_factory(**_kwargs):
    return FakeSession()


def test_vision_service_sends_image_and_parses_caption(tmp_path):
    image = tmp_path / "sample.png"
    Image.new("RGB", (32, 24), "white").save(image)
    profile = validate_profile(
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
    result = asyncio.run(
        VisionCaptionService(session_factory=fake_session_factory).caption(
            profile,
            image,
            prompt_template="请用 {{language}} 描述图片。",
            language="zh-CN",
        )
    )
    assert result.caption == "一只猫。"

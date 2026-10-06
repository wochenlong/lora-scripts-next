import asyncio

import pytest
from PIL import Image

from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.llm.contracts import LLMContractError
from mikazuki.llm.service import UnifiedLLMService


@pytest.fixture
def service(tmp_path):
    store = UnifiedConfigStore(tmp_path / "translation.json")
    store.save({"profiles": [
        {"id": identifier, "name": identifier,
         "endpoint": "http://127.0.0.1:8080/v1/chat/completions", "model": identifier,
         "source": source, "capabilities": ["text", "vision"], "languages": ["zh-CN"]}
        for identifier, source in [("remote", "remote"), ("local", "managed-local")]
    ]})
    return UnifiedLLMService(store)


def test_connection_test_targets_selected_local_and_sends_safe_image(service, tmp_path, monkeypatch):
    image_path = tmp_path / "private-name.png"
    Image.new("RGB", (32, 32), "white").save(image_path)
    calls = []

    async def completion(profile, payload, **kwargs):
        calls.append((profile.id, payload))
        return {"choices": [{"finish_reason": "stop"}]}, '{"ok":true}'

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", completion)
    result = asyncio.run(service.connection_test(capability="vision", profile_id="local", image_path=image_path))
    assert result["profile_id"] == "local"
    assert result["ok"] is True
    assert "content" not in result
    assert len(calls) == 1
    assert calls[0][1]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert str(image_path) not in str(calls)


@pytest.mark.parametrize("content,reason", [
    ('{"ok":false}', "stop"), ('{"ok":1}', "stop"),
    ('{"ok":true,"secret":"example"}', "stop"), ('not JSON', "stop"),
    ('{"ok":true}', "length"),
])
def test_connection_test_rejects_invalid_or_truncated_results(service, monkeypatch, content, reason):
    async def completion(*args, **kwargs):
        return {"choices": [{"finish_reason": reason}]}, content

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", completion)
    with pytest.raises(LLMContractError):
        asyncio.run(service.connection_test(profile_id="remote"))


def test_connection_test_does_not_hide_failure_by_using_fallback(service, monkeypatch):
    calls = []

    async def completion(profile, *args, **kwargs):
        calls.append(profile.id)
        raise RuntimeError("endpoint unavailable")

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", completion)
    with pytest.raises(RuntimeError):
        asyncio.run(service.connection_test(profile_id="remote"))
    assert calls == ["remote"]


@pytest.mark.parametrize("capability", ["text", "vision"])
def test_production_requests_never_fallback_without_explicit_enable(service, tmp_path, monkeypatch, capability):
    from mikazuki.llm.http import LLMRequestError
    image = tmp_path / "sample.png"
    Image.new("RGB", (32, 32)).save(image)
    calls = []

    async def completion(profile, *args, **kwargs):
        calls.append(profile.id)
        raise LLMRequestError("remote unavailable", "llm_unreachable")

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", completion)
    operation = service.complete_text("hello") if capability == "text" else service.complete_vision(image, "hello")
    with pytest.raises(LLMRequestError):
        asyncio.run(operation)
    assert calls == ["remote"]

import asyncio

import pytest
from PIL import Image

from mikazuki.llm.config import UnifiedConfigStore, config_revision
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
    ], "local_fallback_enabled": False})
    for identifier in ("remote", "local"):
        selected = next(item for item in store.load()["profiles"] if item["id"] == identifier)
        for capability in ("text", "vision"):
            store.record_verification(identifier, config_revision(selected), capability)
    return UnifiedLLMService(store)


def test_connection_test_targets_selected_local_and_sends_safe_image(service, tmp_path, monkeypatch):
    image_path = tmp_path / "private-name.png"
    Image.new("RGB", (32, 32), "white").save(image_path)
    calls = []

    async def completion(profile, payload, **kwargs):
        calls.append((profile.id, payload))
        return {"choices": [{"finish_reason": "stop"}]}, '{"red_shape":"square","blue_shape":"circle","green_shape":"triangle"}'

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
def test_production_requests_respect_disabled_shared_fallback(service, tmp_path, monkeypatch, capability):
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


@pytest.mark.parametrize("vision_supported", [False, True])
def test_automatic_detection_enables_only_proven_capabilities(service, monkeypatch, vision_supported):
    import json
    from mikazuki.llm.contracts import LLMRouteError
    # Start from a legacy text-only declaration; discovery must still test vision.
    config = service.config_store.load()
    config["profiles"][0]["capabilities"] = ["text"]
    service.config_store.save({"profiles": config["profiles"]})
    calls = []

    async def completion(profile, payload, **kwargs):
        calls.append((profile.id, payload))
        visual = isinstance(payload["messages"][-1]["content"], list)
        response = ({"red_shape": "square", "blue_shape": "circle", "green_shape": "triangle"}
                    if visual and vision_supported else {"translation": "红色圆形在蓝色方块的左侧。", "language": "zh-CN"})
        return {"choices": [{"finish_reason": "stop"}]}, json.dumps(response, ensure_ascii=False)

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", completion)
    result = asyncio.run(service.connection_test(capability=None, profile_id="remote"))
    expected = ["text", "vision"] if vision_supported else ["text"]
    profile = service.config_store.load()["profiles"][0]
    assert profile["capabilities"] == profile["verified_capabilities"] == expected
    assert result["verified_capabilities"] == expected
    assert result["vision_error_code"] is None if vision_supported else result["vision_error_code"]
    assert [item[0] for item in calls] == ["remote", "remote"]
    assert service.resolve("text").id == "remote"
    if vision_supported:
        assert service.resolve("vision").id == "remote"
    else:
        with pytest.raises(LLMRouteError):
            service.resolve("vision")


def test_automatic_detection_does_not_apply_stale_verification(service, monkeypatch):
    import json
    from mikazuki.llm.contracts import LLMConfigConflict
    requests = 0

    async def completion(profile, payload, **kwargs):
        nonlocal requests
        requests += 1
        if requests == 2:
            config = service.config_store.load()
            config["profiles"][0]["model"] = "changed-model"
            service.config_store.save({"profiles": config["profiles"]})
        response = ({"translation": "红色圆形位于蓝色方块的左侧。", "language": "zh-CN"}
                    if requests == 1 else {"red_shape": "square", "blue_shape": "circle", "green_shape": "triangle"})
        return {"choices": [{"finish_reason": "stop"}]}, json.dumps(response, ensure_ascii=False)

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", completion)
    with pytest.raises(LLMConfigConflict):
        asyncio.run(service.connection_test(capability=None, profile_id="remote"))
    selected = service.config_store.load()["profiles"][0]
    assert selected["model"] == "changed-model"
    assert selected["verified_capabilities"] == []


def test_shared_defaults_enable_caches_and_fallback_but_preserve_disabled_value(tmp_path):
    store = UnifiedConfigStore(tmp_path / "llm.json")
    initial = store.load()
    assert initial["local_fallback_enabled"] is True
    assert initial["cache"] == {"translation": True, "caption": True}
    store.save({"local_fallback_enabled": False})
    assert store.load()["local_fallback_enabled"] is False

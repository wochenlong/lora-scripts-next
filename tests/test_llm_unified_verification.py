"""Shared profile authority, real-response verification and ordered failover contracts."""
import asyncio
import json

import pytest

from mikazuki.llm.config import UnifiedConfigStore, config_revision
from mikazuki.llm.contracts import LLMConfigConflict, LLMContractError, LLMRouteError
from mikazuki.llm.http import LLMRequestError
from mikazuki.llm.service import UnifiedLLMService


def profile(identifier="remote", **overrides):
    return {"id": identifier, "name": identifier, "endpoint": "https://example.test/v1/chat/completions",
            "model": "vision-model", "source": "remote", "capabilities": ["text", "vision"],
            "languages": ["en", "zh-CN"], "api_key": "runtime-test-key", **overrides}


def trusted(store, identifier, capabilities=("text", "vision")):
    for capability in capabilities:
        selected = next(item for item in store.load()["profiles"] if item["id"] == identifier)
        store.record_verification(identifier, config_revision(selected), capability)


@pytest.fixture
def store(tmp_path):
    result = UnifiedConfigStore(tmp_path / "shared.json")
    result.save({"profiles": [profile()]})
    return result


def test_client_cannot_forge_ready_or_verified_capabilities(store):
    state = store.load()
    forged = {**state["profiles"][0], "ready": True, "verified_capabilities": ["text", "vision"],
              "verification": {"fingerprint": config_revision(state["profiles"][0]), "capabilities": ["text", "vision"]}}
    store.save({"profiles": [forged], "revision": state["revision"]})
    saved = store.load()["profiles"][0]
    assert saved["ready"] is False
    assert saved["verified_capabilities"] == []
    with pytest.raises(LLMRouteError):
        UnifiedLLMService(store).resolve("vision")


@pytest.mark.parametrize("change", [
    {"endpoint": "https://changed.test/v1/chat/completions"}, {"model": "changed"},
    {"capabilities": ["text"]}, {"languages": ["en"]}, {"api_key": "changed-runtime-key"},
    {"metadata": {"reasoning_effort": "high"}},
])
def test_connection_changes_invalidate_backend_verification_and_cache_identity(store, change):
    trusted(store, "remote")
    previous = store.load()["profiles"][0]
    store.save({"profiles": [{**previous, **change}]})
    current = store.load()["profiles"][0]
    assert current["verified_capabilities"] == []
    assert not current["ready"]
    assert config_revision(current) != config_revision(previous)


def test_cosmetic_name_change_preserves_capability_verification(store):
    trusted(store, "remote")
    previous = store.load()["profiles"][0]
    saved = store.save({"profiles": [{**previous, "name": "A friendly name"}]})["profiles"][0]
    assert saved["ready"] and saved["verified_capabilities"] == ["text", "vision"]
    assert config_revision(saved) == config_revision(previous)


def test_configuration_compare_and_swap_is_atomic(store):
    revision = store.load()["revision"]
    store.save({"revision": revision, "cache": {"translation": False, "caption": True}})
    before = store.path.read_bytes()
    with pytest.raises(LLMConfigConflict):
        store.save({"revision": revision, "profiles": []})
    assert store.path.read_bytes() == before


def test_late_verification_cannot_verify_changed_endpoint(store):
    previous = store.load()["profiles"][0]
    store.save({"profiles": [{**previous, "endpoint": "https://new.test/v1/chat/completions"}]})
    with pytest.raises(LLMConfigConflict):
        store.record_verification("remote", config_revision(previous), "vision")
    assert store.load()["profiles"][0]["verified_capabilities"] == []


def test_remote_credentials_are_runtime_only_and_required_after_restart(store, monkeypatch):
    trusted(store, "remote")
    assert store.load()["profiles"][0]["ready"]
    assert "runtime-test-key" not in store.path.read_text()
    from mikazuki.llm import secrets
    monkeypatch.setattr(secrets, "_credentials", {})
    assert not store.load()["profiles"][0]["ready"]
    with pytest.raises(LLMRouteError):
        UnifiedLLMService(store).resolve("text")


def test_anonymous_loopback_remote_remains_supported_after_real_verification(store):
    store.save({"profiles": [profile(api_key="", endpoint="http://127.0.0.1:18080/v1/chat/completions")]})
    trusted(store, "remote")
    assert UnifiedLLMService(store).resolve("text").id == "remote"


def test_failed_diagnostic_revokes_only_the_tested_capability(store, monkeypatch):
    trusted(store, "remote")

    async def failure(*_args, **_kwargs):
        return {"choices": [{"finish_reason": "stop"}]}, '{"red_shape":"circle","blue_shape":"square","green_shape":"triangle"}'

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", failure)
    with pytest.raises(LLMContractError):
        asyncio.run(UnifiedLLMService(store).connection_test(profile_id="remote", capability="vision"))
    assert store.load()["profiles"][0]["verified_capabilities"] == ["text"]
    with pytest.raises(LLMRouteError):
        UnifiedLLMService(store).resolve("vision")
    assert UnifiedLLMService(store).resolve("text").id == "remote"


def test_unverified_profile_can_run_exact_selected_text_and_internal_image_diagnostics(store, monkeypatch):
    observed = []

    async def actual_response(selected, payload, **_kwargs):
        observed.append((selected.id, payload))
        content = payload["messages"][-1]["content"]
        value = ({"red_shape": "square", "blue_shape": "circle", "green_shape": "triangle"}
                 if isinstance(content, list) else {"translation": "红色圆形位于蓝色方块的左侧。", "language": "zh-CN"})
        return {"choices": [{"finish_reason": "stop"}]}, json.dumps(value, ensure_ascii=False)

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", actual_response)
    service = UnifiedLLMService(store)
    first = asyncio.run(service.connection_test(profile_id="remote", capability="text"))
    assert first["verified_capabilities"] == ["text"]
    with pytest.raises(LLMRouteError):
        service.resolve("vision")
    second = asyncio.run(service.connection_test(profile_id="remote", capability="vision"))
    assert second["verified_capabilities"] == ["text", "vision"]
    assert service.resolve("vision").id == "remote"
    assert len(observed) == 2
    assert observed[1][1]["response_format"]["json_schema"]["strict"] is True
    image = observed[1][1]["messages"][-1]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/jpeg;base64,")
    assert "square" not in observed[1][1]["messages"][-1]["content"][0]["text"].split("Values must be")[0]


@pytest.mark.parametrize("local_enabled", [False, True])
def test_every_remote_is_attempted_before_explicit_local_fallback(store, monkeypatch, local_enabled):
    store.save({"profiles": [profile("one"), profile("two"), profile("local", source="local-endpoint", api_key="", endpoint="http://127.0.0.1:18080/v1/chat/completions")],
                "local_fallback_enabled": local_enabled, "routes": {"translation": "two"}})
    for identifier in ("one", "two", "local"):
        trusted(store, identifier)
    observed = []

    async def request(selected, _payload, **_kwargs):
        observed.append(selected.id)
        if selected.is_remote:
            raise LLMRequestError("unreachable", "llm_unreachable")
        return {"choices": [{"finish_reason": "stop"}]}, "local response"

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", request)
    operation = UnifiedLLMService(store).complete_text("hello", language="zh-CN")
    if local_enabled:
        assert asyncio.run(operation)[0].id == "local"
        assert observed == ["two", "one", "local"]
    else:
        with pytest.raises(LLMRequestError):
            asyncio.run(operation)
        assert observed == ["two", "one"]


def test_global_fallback_never_changes_remote_first_policy(store):
    store.save({"profiles": [profile("local", source="local-endpoint", api_key="", endpoint="http://127.0.0.1:18080/v1/chat/completions"), profile()],
                "local_fallback_enabled": True})
    trusted(store, "remote")
    trusted(store, "local")
    assert UnifiedLLMService(store).resolve("text", profile_id="local").id == "remote"

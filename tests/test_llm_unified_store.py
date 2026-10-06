from pathlib import Path
import asyncio
import pytest

from mikazuki.llm.config import SECRET_MASK, UnifiedConfigStore, config_revision
from mikazuki.llm.routing import choose_profile
from mikazuki.llm.service import UnifiedLLMService
from mikazuki.tag_translation.translation_config import OnlineServiceConfig


def remote_profile(profile_id="remote"):
    return {
        "id": profile_id,
        "name": "Remote",
        "endpoint": "https://example.test/v1/chat/completions",
        "model": "vision-model",
        "source": "remote",
        "capabilities": ["text", "vision"],
        "languages": ["zh-CN", "en"],
        "api_key": "secret",
    }


def test_unified_store_masks_key_and_keeps_legacy_translation_fields(tmp_path: Path):
    path = tmp_path / "translation.json"
    store = UnifiedConfigStore(path)
    saved = store.save({"profiles": [remote_profile()], "routes": {"translation": "remote", "caption": "remote"}})
    assert saved["version"] == 5
    masked = store.load_masked()
    assert masked["profiles"][0]["api_key"] == SECRET_MASK
    raw = path.read_text(encoding="utf-8")
    assert '"api_key": "secret"' not in raw
    assert '"api_key": "********"' in raw
    assert '"llm"' in raw
    assert store.load()["profiles"][0]["api_key"] == "secret"


def test_unified_store_accepts_masked_update_without_erasing_secret(tmp_path: Path):
    store = UnifiedConfigStore(tmp_path / "translation.json")
    store.save({"profiles": [remote_profile()]})
    store.save({"profiles": [{**remote_profile(), "api_key": SECRET_MASK, "name": "Changed"}]})
    assert store.load()["profiles"][0]["api_key"] == "secret"
    assert store.load()["profiles"][0]["name"] == "Changed"


def test_legacy_translation_manager_reads_shared_selected_remote_profile(tmp_path: Path):
    path = tmp_path / "translation.json"
    store = UnifiedConfigStore(path)
    store.save({"profiles": [remote_profile()]})
    legacy = OnlineServiceConfig(path).load()
    assert legacy["active_remote_id"] == "remote"
    assert legacy["deepseek"]["endpoint"].endswith("/chat/completions")
    assert legacy["remote_profiles"][0]["model"] == "vision-model"


def test_legacy_translation_save_preserves_shared_llm_profiles(tmp_path: Path):
    path = tmp_path / "translation.json"
    store = UnifiedConfigStore(path)
    store.save({"profiles": [remote_profile()]})
    legacy_store = OnlineServiceConfig(path)
    config = legacy_store.load()
    config["active_remote_id"] = "remote"
    legacy_store.save(config)
    assert UnifiedConfigStore(path).load()["profiles"][0]["id"] == "remote"


def test_legacy_translation_mask_hides_nested_shared_profile_key(tmp_path: Path):
    path = tmp_path / "translation.json"
    UnifiedConfigStore(path).save({"profiles": [remote_profile()]})
    masked = OnlineServiceConfig(path).load()
    from mikazuki.tag_translation.translation_config import mask_config
    assert mask_config(masked)["llm"]["profiles"][0]["api_key"] == SECRET_MASK


def test_legacy_save_updates_shared_model_key_and_cache_revision(tmp_path):
    path = tmp_path / "translation.json"
    shared = UnifiedConfigStore(path)
    shared.save({"profiles": [remote_profile()]})
    old = shared.load()["profiles"][0]
    OnlineServiceConfig(path).save({
        "remote_profiles": [{
            "id": "remote",
            "name": "Changed",
            "endpoint": "https://example.test/v1/chat/completions",
            "model": "new-model",
            "api_key": "new-secret",
        }],
        "active_remote_id": "remote",
    })
    profile = shared.load()["profiles"][0]
    assert profile["model"] == "new-model"
    assert profile["api_key"] == "new-secret"
    assert profile["capabilities"] == ["text", "vision"]
    assert config_revision(profile) != config_revision(old)


def test_empty_config_can_remove_all_profiles(tmp_path):
    store = UnifiedConfigStore(tmp_path / "translation.json")
    store.save({"profiles": [remote_profile()]})
    store.save({"profiles": []})
    assert store.load()["profiles"] == []


@pytest.mark.parametrize("change", [
    {"enabled": "false"}, {"capabilities": "vision"}, {"languages": "zh-CN"}, {"id": ""},
])
def test_invalid_profile_values_rejected_without_overwriting_config(tmp_path, change):
    from mikazuki.llm.contracts import LLMContractError
    store = UnifiedConfigStore(tmp_path / "translation.json")
    store.save({"profiles": [remote_profile()]})
    before = store.path.read_bytes()
    with pytest.raises(LLMContractError):
        store.save({"profiles": [{**remote_profile(), **change}]})
    assert store.path.read_bytes() == before


def test_selected_text_only_profile_cannot_be_used_for_caption(tmp_path):
    from mikazuki.llm.contracts import LLMRouteError
    store = UnifiedConfigStore(tmp_path / "translation.json")
    store.save({"profiles": [remote_profile(), {**remote_profile("text"), "capabilities": ["text"]}]})
    with pytest.raises(LLMRouteError) as error:
        UnifiedLLMService(store).resolve("vision", profile_id="text")
    assert error.value.code == "llm_capability_vision_required"


def test_remote_profile_is_always_before_local_fallback():
    profiles = [
        {**remote_profile(), "ready": True},
        {
            "id": "local",
            "name": "Local",
            "endpoint": "http://127.0.0.1:8080/v1/chat/completions",
            "model": "qwen",
            "source": "managed-local",
            "capabilities": ["vision"],
            "languages": ["zh-CN"],
            "ready": True,
        },
    ]
    assert choose_profile(profiles, "vision", language="zh-CN", preferred_id="local").id == "remote"


def test_revision_excludes_api_key(tmp_path: Path):
    store = UnifiedConfigStore(tmp_path / "translation.json")
    profile = remote_profile()
    first = config_revision(profile)
    profile["api_key"] = "different"
    assert config_revision(profile) == first


def test_remote_failure_uses_configured_local_fallback(tmp_path, monkeypatch):
    store = UnifiedConfigStore(tmp_path / "translation.json")
    store.save({
        "profiles": [
            remote_profile(),
            {
                "id": "local",
                "name": "Local",
                "endpoint": "http://127.0.0.1:8080/v1/chat/completions",
                "model": "local",
                "source": "managed-local",
                "capabilities": ["text", "vision"],
                "languages": ["zh-CN"],
            },
        ],
    })
    calls = []

    async def fake_completion(profile, payload, **kwargs):
        calls.append(profile.id)
        if profile.id == "remote":
            from mikazuki.llm.http import LLMRequestError
            raise LLMRequestError("remote unavailable", "llm_unreachable")
        return {"choices": [{"message": {"content": "local"}, "finish_reason": "stop"}]}, "local"

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", fake_completion)
    service = UnifiedLLMService(store)
    profile, _envelope, content = asyncio.run(service.complete_text("hello", language="zh-CN", allow_local_fallback=True))
    assert profile.id == "local"
    assert content == "local"
    assert calls == ["remote", "local"]

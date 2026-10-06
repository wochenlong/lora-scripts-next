from pathlib import Path
import asyncio

from mikazuki.llm.config import SECRET_MASK, UnifiedConfigStore, config_revision
from mikazuki.llm.routing import choose_profile
from mikazuki.llm.service import UnifiedLLMService


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
    assert '"api_key": "secret"' in raw
    assert '"llm"' in raw
    assert store.load()["profiles"][0]["api_key"] == "secret"


def test_unified_store_accepts_masked_update_without_erasing_secret(tmp_path: Path):
    store = UnifiedConfigStore(tmp_path / "translation.json")
    store.save({"profiles": [remote_profile()]})
    store.save({"profiles": [{**remote_profile(), "api_key": SECRET_MASK, "name": "Changed"}]})
    assert store.load()["profiles"][0]["api_key"] == "secret"
    assert store.load()["profiles"][0]["name"] == "Changed"


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
            raise RuntimeError("remote unavailable")
        return {"choices": [{"message": {"content": "local"}, "finish_reason": "stop"}]}, "local"

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", fake_completion)
    service = UnifiedLLMService(store)
    profile, _envelope, content = asyncio.run(service.complete_text("hello", language="zh-CN"))
    assert profile.id == "local"
    assert content == "local"
    assert calls == ["remote", "local"]

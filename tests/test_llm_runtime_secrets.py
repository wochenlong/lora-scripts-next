import json

import pytest

from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.llm import secrets
from mikazuki.tag_translation.translation_config import OnlineServiceConfig


def profile(identifier="one", key="runtime-only-value"):
    return {"id": identifier, "name": identifier, "model": "text-model",
            "endpoint": "https://example.test/v1/chat/completions", "api_key": key}


def test_shared_and_legacy_stores_persist_only_masks_and_share_runtime_credentials(tmp_path):
    path = tmp_path / "translation.json"
    shared = UnifiedConfigStore(path)
    shared.save({"profiles": [profile()]})
    assert "runtime-only-value" not in path.read_text(encoding="utf-8")
    assert OnlineServiceConfig(path).load()["deepseek"]["api_key"] == "runtime-only-value"
    OnlineServiceConfig(path).save({"deepseek": {"api_key": "updated-runtime-value"}})
    assert shared.load()["profiles"][0]["api_key"] == "updated-runtime-value"
    assert "updated-runtime-value" not in path.read_text(encoding="utf-8")


def test_masks_cannot_be_used_as_credentials_after_process_restart(tmp_path, monkeypatch):
    store = UnifiedConfigStore(tmp_path / "translation.json")
    store.save({"profiles": [profile()]})
    monkeypatch.setattr(secrets, "_credentials", {})
    assert store.load()["profiles"][0]["api_key"] == ""
    assert store.load_masked()["profiles"][0]["api_key_configured"] is False
    store.save({"profiles": [profile(key="injected-after-restart")]})
    assert store.load()["profiles"][0]["api_key"] == "injected-after-restart"
    assert "injected-after-restart" not in store.path.read_text(encoding="utf-8")


def test_reordering_and_removal_do_not_mix_or_resurrect_secrets(tmp_path):
    store = UnifiedConfigStore(tmp_path / "translation.json")
    store.save({"profiles": [profile("a", "first-key"), profile("b", "second-key")]})
    store.save({"profiles": [profile("b", secrets.MASK), profile("a", secrets.MASK)]})
    assert [item["api_key"] for item in store.load()["profiles"]] == ["second-key", "first-key"]
    store.save({"profiles": []})
    store.save({"profiles": [profile("a", "")]})
    assert store.load()["profiles"][0]["api_key"] == ""


def test_legacy_plaintext_is_scrubbed_on_first_read(tmp_path):
    path = tmp_path / "translation.json"
    path.write_text(json.dumps({"deepseek": {"api_key": "old-plaintext"}}))
    assert OnlineServiceConfig(path).load()["deepseek"]["api_key"] == "old-plaintext"
    assert "old-plaintext" not in path.read_text(encoding="utf-8")


def test_failed_atomic_write_does_not_change_runtime_secret(tmp_path, monkeypatch):
    store = UnifiedConfigStore(tmp_path / "translation.json")
    store.save({"profiles": [profile()]})
    before = store.path.read_bytes()

    def failed_replace(*args):
        raise OSError("cannot replace")

    monkeypatch.setattr(secrets.os, "replace", failed_replace)
    with pytest.raises(OSError):
        store.save({"profiles": [profile(key="not-committed")]})
    assert store.path.read_bytes() == before
    assert store.load()["profiles"][0]["api_key"] == "runtime-only-value"
    assert not list(tmp_path.glob("*.tmp"))

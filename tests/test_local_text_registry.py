"""Shared local Qwen profile registration contracts.

The old text-only manager was replaced by the single managed visual/text
service. These tests exercise durable profile behavior without starting a
real llama.cpp process.
"""

import sys
from types import ModuleType
from unittest.mock import Mock, call

from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.llm.local_text import LocalTextModelService
from mikazuki.llm.local_vision import LocalVisionService
from mikazuki.tag_translation.translation_config import OnlineServiceConfig


def make_service(tmp_path):
    path = tmp_path / "translation.json"
    legacy = OnlineServiceConfig(path)
    legacy.save({})
    shared = UnifiedConfigStore(path)
    shared.save(shared.load())
    service = LocalVisionService(tmp_path, legacy, shared)
    service._runtime_port = 18099
    return service, shared


def test_shared_profile_registers_once_and_preserves_user_fields(tmp_path):
    service, shared = make_service(tmp_path)

    service._register_verified()
    config = shared.load()
    asset_id = service._profile().asset_id
    selected = next(profile for profile in config["profiles"] if profile["id"] == asset_id)
    assert selected["capabilities"] == ["text", "vision"]
    assert selected["verified_capabilities"] == ["text", "vision"]
    assert selected["ready"] is True
    selected.update(name="Custom shared model", enabled=False,
                    metadata={"translation_system_prompt": "Keep this prompt"})
    shared.save({"profiles": config["profiles"]})

    service._register_verified()
    profiles = shared.load()["profiles"]
    matching = [profile for profile in profiles if profile["asset_id"] == asset_id]
    assert len(matching) == 1
    profile = matching[0]
    assert profile["capabilities"] == ["text", "vision"]
    assert profile["ready"] is False
    assert profile["name"] == "Custom shared model"
    assert profile["enabled"] is False
    assert profile["metadata"]["translation_system_prompt"] == "Keep this prompt"
    assert profile["endpoint"] == "http://127.0.0.1:18099/v1/chat/completions"

    service._invalidate()
    invalidated = next(profile for profile in shared.load()["profiles"] if profile["asset_id"] == asset_id)
    assert invalidated["verification"]["capabilities"] == []
    assert invalidated["verified_capabilities"] == []
    assert invalidated["name"] == "Custom shared model"
    assert invalidated["enabled"] is False


def test_legacy_text_alias_resolves_to_shared_visual_service(tmp_path, monkeypatch):
    service, shared = make_service(tmp_path)
    # Replace only the alias's lazy runtime dependency: importing the real
    # runtime here would initialize shared-root SQLite state, and returning
    # its actual singleton would make this test depend on installed assets.
    runtime = ModuleType("mikazuki.llm.runtime")
    runtime.get_local_vision_service = Mock(return_value=service)
    monkeypatch.setitem(sys.modules, "mikazuki.llm.runtime", runtime)

    alias = LocalTextModelService(tmp_path, OnlineServiceConfig(shared.path), shared)
    ignored_root = tmp_path / "ignored-legacy-model-root"
    second_alias = LocalTextModelService(ignored_root, OnlineServiceConfig(ignored_root / "translation.json"))

    assert alias is service
    assert second_alias is service
    assert alias.translation_root == tmp_path
    assert alias.unified_config_store is shared
    assert not ignored_root.exists()
    assert runtime.get_local_vision_service.call_args_list == [call(), call()]

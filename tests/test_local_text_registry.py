import asyncio
import pytest

from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.llm.local_text import ASSET_ID, LocalTextModelService
from mikazuki.tag_translation.local_model_service import LocalModelService
from mikazuki.tag_translation.translation_config import OnlineServiceConfig


def test_existing_text_runtime_registers_once_in_shared_profiles_and_stops(tmp_path, monkeypatch):
    path = tmp_path / "translation.json"
    legacy = OnlineServiceConfig(path)
    legacy.save({})
    shared = UnifiedConfigStore(path)
    shared.save(shared.load())
    service = LocalTextModelService(tmp_path / "models", legacy, shared)
    service._runtime_port = 18099

    async def started(_self):
        return {"state": "running", "runtime_version": "b11327"}

    async def stopped(_self):
        return {"state": "ready"}

    monkeypatch.setattr(LocalModelService, "start_runtime", started)
    monkeypatch.setattr(LocalModelService, "stop_runtime", stopped)
    async def verify():
        await service.start_runtime()
        config = shared.load()
        selected = next(profile for profile in config["profiles"] if profile["asset_id"] == ASSET_ID)
        selected.update(name="Custom text model", enabled=False, metadata={"translation_system_prompt": "Keep this prompt"})
        shared.save({"profiles": config["profiles"]})
        await service.start_runtime()
        profiles = shared.load()["profiles"]
        assert len([profile for profile in profiles if profile["asset_id"] == ASSET_ID]) == 1
        profile = next(profile for profile in profiles if profile["asset_id"] == ASSET_ID)
        assert profile["capabilities"] == ["text"]
        assert profile["ready"] is True
        assert profile["name"] == "Custom text model"
        assert profile["enabled"] is False
        assert profile["metadata"]["translation_system_prompt"] == "Keep this prompt"
        assert profile["endpoint"] == "http://127.0.0.1:18099/v1/chat/completions"
        await service.stop_runtime()
        assert next(profile for profile in shared.load()["profiles"] if profile["asset_id"] == ASSET_ID)["ready"] is False
    asyncio.run(verify())
    profile = next(profile for profile in shared.load()["profiles"] if profile["asset_id"] == ASSET_ID)
    profile["capabilities"] = ["text", "vision"]
    from mikazuki.llm.config import LLMContractError
    with pytest.raises(LLMContractError, match="text-only"):
        shared.save({"profiles": [profile]})


def test_visual_runtime_restart_preserves_shared_translation_prompt(tmp_path, monkeypatch):
    from mikazuki.llm.local_vision import ASSET_ID as vision_id, LocalVisionService
    path = tmp_path / "translation.json"
    legacy = OnlineServiceConfig(path)
    legacy.save({})
    shared = UnifiedConfigStore(path)
    shared.save(shared.load())
    service = LocalVisionService(tmp_path, legacy, shared)
    service._runtime_port = 18098
    async def started(_self):
        return {"state": "running"}
    monkeypatch.setattr(LocalModelService, "start_runtime", started)
    async def verify():
        await service.start_runtime()
        config = shared.load()
        selected = next(profile for profile in config["profiles"] if profile["id"] == vision_id)
        selected.update(name="Custom vision model", enabled=False, metadata={"translation_system_prompt": "Keep vision text prompt"})
        shared.save({"profiles": config["profiles"]})
        await service.start_runtime()
        selected = next(profile for profile in shared.load()["profiles"] if profile["id"] == vision_id)
        assert selected["enabled"] is False
        assert selected["name"] == "Custom vision model"
        assert selected["metadata"]["translation_system_prompt"] == "Keep vision text prompt"
    asyncio.run(verify())

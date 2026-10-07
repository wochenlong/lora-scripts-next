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
        await service.start_runtime()
        profiles = shared.load()["profiles"]
        assert len([profile for profile in profiles if profile["asset_id"] == ASSET_ID]) == 1
        profile = next(profile for profile in profiles if profile["asset_id"] == ASSET_ID)
        assert profile["capabilities"] == ["text"]
        assert profile["ready"] is True
        assert profile["endpoint"] == "http://127.0.0.1:18099/v1/chat/completions"
        await service.stop_runtime()
        assert next(profile for profile in shared.load()["profiles"] if profile["asset_id"] == ASSET_ID)["ready"] is False
    asyncio.run(verify())
    profile = next(profile for profile in shared.load()["profiles"] if profile["asset_id"] == ASSET_ID)
    profile["capabilities"] = ["text", "vision"]
    from mikazuki.llm.config import LLMContractError
    with pytest.raises(LLMContractError, match="text-only"):
        shared.save({"profiles": [profile]})

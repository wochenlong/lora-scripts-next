"""Register the existing optional translation runtime in the shared registry."""

from mikazuki.tag_translation.local_model_service import LocalModelService, MODEL_ID

ASSET_ID = "qwen3.5-0.8b-local"


class LocalTextModelService(LocalModelService):
    def __init__(self, root, config_store, unified_config_store):
        super().__init__(root, config_store)
        self.unified_config_store = unified_config_store

    async def start_runtime(self):
        status = await super().start_runtime()
        current = self.unified_config_store.load()
        profiles = [profile for profile in current["profiles"] if profile.get("asset_id") != ASSET_ID]
        previous = next((profile for profile in current["profiles"] if profile.get("asset_id") == ASSET_ID), {})
        profiles.append({
            "id": ASSET_ID, "name": previous.get("name", "Qwen3.5-0.8B（纯文本）"), "source": "managed-local",
            "endpoint": self.upstream_endpoint(), "model": MODEL_ID,
            "capabilities": ["text"], "languages": ["zh-CN", "zh-TW", "en", "ja"],
            "api_key": "", "asset_id": ASSET_ID, "revision": status.get("runtime_version"),
            "enabled": previous.get("enabled", True), "ready": status["state"] == "running",
            "metadata": previous.get("metadata", {}),
        })
        self.unified_config_store.save({"profiles": profiles})
        return status

    async def stop_runtime(self):
        status = await super().stop_runtime()
        current = self.unified_config_store.load()
        changed = False
        for profile in current["profiles"]:
            if profile.get("asset_id") == ASSET_ID:
                profile["ready"] = False
                changed = True
        if changed:
            self.unified_config_store.save({"profiles": current["profiles"]})
        return status

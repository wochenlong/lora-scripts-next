from __future__ import annotations

import os
from pathlib import Path

import aiohttp

from .config import UnifiedConfigStore
from .cache import CaptionCache
from .service import UnifiedLLMService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRANSLATION_ROOT = Path(
    os.environ.get("MIKAZUKI_TAG_TRANSLATION_ROOT", str(PROJECT_ROOT / "assets" / "tag_translation"))
)
SHARED_CONFIG_PATH = TRANSLATION_ROOT / "translation.json"
SHARED_CACHE_PATH = TRANSLATION_ROOT / "translations.sqlite3"


def _session_factory(**kwargs):
    kwargs.setdefault("trust_env", True)
    return aiohttp.ClientSession(**kwargs)


llm_config_store = UnifiedConfigStore(SHARED_CONFIG_PATH)
llm_service = UnifiedLLMService(llm_config_store, session_factory=_session_factory)
caption_cache = CaptionCache(SHARED_CACHE_PATH)

_local_vision_service = None


def get_local_vision_service():
    global _local_vision_service
    if _local_vision_service is None:
        from .local_vision import LocalVisionService
        from mikazuki.tag_translation.translation_config import OnlineServiceConfig
        _local_vision_service = LocalVisionService(
            TRANSLATION_ROOT, OnlineServiceConfig(SHARED_CONFIG_PATH), llm_config_store,
        )
    return _local_vision_service

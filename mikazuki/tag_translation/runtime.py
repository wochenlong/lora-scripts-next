"""Runtime wiring for the migrated tag translation services."""

from __future__ import annotations

import os
from pathlib import Path

import aiohttp

from .chinese_dictionary_service import ChineseDictionaryService
from .translation_config import OnlineServiceConfig
from .translation_service import TranslationManager
from .translation_store import TranslationStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRANSLATION_ROOT = Path(
    os.environ.get("MIKAZUKI_TAG_TRANSLATION_ROOT", str(PROJECT_ROOT / "assets" / "tag_translation"))
)
DICTIONARY_ROOT = TRANSLATION_ROOT / "danbooru"
TRANSLATION_CONFIG_PATH = TRANSLATION_ROOT / "translation.json"
TRANSLATION_CACHE_PATH = TRANSLATION_ROOT / "translations.sqlite3"
LOCAL_MODEL_ROOT = TRANSLATION_ROOT / "models"


def _session_factory(**kwargs):
    """Use the host's HTTP proxy and environment policy for all providers."""
    kwargs.setdefault("trust_env", True)
    return aiohttp.ClientSession(**kwargs)


dictionary_service = ChineseDictionaryService(str(DICTIONARY_ROOT), session_factory=_session_factory)
translation_store = TranslationStore(str(TRANSLATION_CACHE_PATH))
translation_manager = TranslationManager(
    str(TRANSLATION_CONFIG_PATH),
    translation_store,
    session_factory=_session_factory,
    primary_store=dictionary_service,
)
class SharedLocalModelFacade:
    """Legacy endpoints delegate to the one shared text/vision runtime."""

    def __getattr__(self, name):
        from mikazuki.llm.runtime import get_local_vision_service
        return getattr(get_local_vision_service(), name)


local_model_service = SharedLocalModelFacade()

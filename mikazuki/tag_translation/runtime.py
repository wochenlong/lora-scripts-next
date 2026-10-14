"""Runtime wiring for the migrated tag translation services."""

from __future__ import annotations

import os
import logging
import sqlite3
from pathlib import Path

import aiohttp

from .chinese_dictionary_service import ChineseDictionaryService
from .dictionary_bundle import DictionaryBundleError, seed_bundle
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
BUNDLED_DICTIONARY_ROOT = Path(os.environ.get(
    "MIKAZUKI_BUNDLED_TAG_DICTIONARY_ROOT", str(PROJECT_ROOT / "assets" / "tag_translation" / "danbooru")
))


def _seed_packaged_dictionary():
    """Populate an empty external data root from verified public package assets."""
    try:
        if (DICTIONARY_ROOT / "tag.sqlite").exists():
            # Updated user dictionaries need structural validation, not the
            # package's pinned hash. Never overwrite an existing user file.
            ChineseDictionaryService._validate_database(str(DICTIONARY_ROOT / "tag.sqlite"))
            return None
        if DICTIONARY_ROOT.resolve() == BUNDLED_DICTIONARY_ROOT.resolve() or not (BUNDLED_DICTIONARY_ROOT / "tag.sqlite").exists():
            return None
        seed_bundle(BUNDLED_DICTIONARY_ROOT, DICTIONARY_ROOT)
    except (DictionaryBundleError, OSError, RuntimeError, sqlite3.Error) as exc:
        logging.getLogger(__name__).warning("Bundled Tag dictionary initialization failed: %s", exc)
        return "本地词库无法读取，请在翻译设置中重试下载词库。"
    return None


def _session_factory(**kwargs):
    """Use the host's HTTP proxy and environment policy for all providers."""
    kwargs.setdefault("trust_env", True)
    return aiohttp.ClientSession(**kwargs)


_dictionary_seed_error = _seed_packaged_dictionary()
dictionary_service = ChineseDictionaryService(str(DICTIONARY_ROOT), session_factory=_session_factory)
if _dictionary_seed_error:
    dictionary_service._runtime.update(state="error", error=_dictionary_seed_error)
    dictionary_service._auto_attempted = True
    dictionary_service._invalid_database = True
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

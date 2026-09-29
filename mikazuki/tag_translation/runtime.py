"""Runtime wiring for the migrated tag translation services."""

from __future__ import annotations

from pathlib import Path

from .chinese_dictionary_service import ChineseDictionaryService
from .translation_config import OnlineServiceConfig
from .translation_service import TranslationManager
from .translation_store import TranslationStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRANSLATION_ROOT = PROJECT_ROOT / "assets" / "tag_translation"
DICTIONARY_ROOT = TRANSLATION_ROOT / "danbooru"
TRANSLATION_CONFIG_PATH = TRANSLATION_ROOT / "translation.json"
TRANSLATION_CACHE_PATH = TRANSLATION_ROOT / "translations.sqlite3"

dictionary_service = ChineseDictionaryService(str(DICTIONARY_ROOT))
translation_store = TranslationStore(str(TRANSLATION_CACHE_PATH))
translation_manager = TranslationManager(
    str(TRANSLATION_CONFIG_PATH),
    translation_store,
    primary_store=dictionary_service,
)


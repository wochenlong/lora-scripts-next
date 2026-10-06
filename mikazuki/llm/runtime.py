from __future__ import annotations

import os
from pathlib import Path

import aiohttp

from .config import UnifiedConfigStore
from .service import UnifiedLLMService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRANSLATION_ROOT = Path(
    os.environ.get("MIKAZUKI_TAG_TRANSLATION_ROOT", str(PROJECT_ROOT / "assets" / "tag_translation"))
)
SHARED_CONFIG_PATH = TRANSLATION_ROOT / "translation.json"


def _session_factory(**kwargs):
    kwargs.setdefault("trust_env", True)
    return aiohttp.ClientSession(**kwargs)


llm_config_store = UnifiedConfigStore(SHARED_CONFIG_PATH)
llm_service = UnifiedLLMService(llm_config_store, session_factory=_session_factory)

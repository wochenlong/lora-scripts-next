from __future__ import annotations

import pytest

from mikazuki.llm.config import (
    SECRET_MASK,
    config_revision,
    mask_profiles,
    migrate_legacy_translation_config,
    validate_profile,
)
from mikazuki.llm.contracts import LLMRouteError
from mikazuki.llm.routing import choose_profile


def test_legacy_translation_config_migrates_to_text_profile():
    config = migrate_legacy_translation_config(
        {
            "version": 4,
            "deepseek": {
                "endpoint": "https://api.example.com/v1/chat/completions",
                "model": "text-model",
                "api_key": "secret",
            },
            "active_remote_id": "default",
        }
    )
    assert config["version"] == 5
    assert config["routes"]["translation"] == "remote-default"
    assert config["profiles"][0]["capabilities"] == ["text"]
    assert config["profiles"][0]["api_key"] == "secret"


def test_migration_is_idempotent_for_v5():
    original = {
        "version": 5,
        "profiles": [
            {
                "id": "remote",
                "name": "Remote",
                "endpoint": "https://api.example.com/v1/chat/completions",
                "model": "vision",
                "source": "remote",
                "capabilities": ["text", "vision"],
                "languages": ["zh-CN"],
            }
        ],
        "routes": {"translation": "remote", "caption": "remote"},
    }
    migrated = migrate_legacy_translation_config(original)
    assert migrated["profiles"][0]["capabilities"] == ["text", "vision"]
    assert migrated["routes"] == original["routes"]


def test_mask_profiles_never_returns_api_key():
    config = migrate_legacy_translation_config(
        {
            "deepseek": {
                "endpoint": "https://api.example.com/v1/chat/completions",
                "model": "m",
                "api_key": "secret",
            }
        }
    )
    masked = mask_profiles(config)
    assert masked["profiles"][0]["api_key"] == SECRET_MASK
    assert masked["profiles"][0]["api_key_configured"] is True
    assert config["profiles"][0]["api_key"] == "secret"


def test_revision_excludes_secret_and_changes_with_capability():
    base = validate_profile(
        {
            "id": "one",
            "name": "One",
            "endpoint": "https://api.example.com/v1/chat/completions",
            "model": "m",
            "source": "remote",
            "capabilities": ["text"],
            "languages": ["en"],
            "api_key": "one-secret",
        }
    )
    vision = dict(base, capabilities=["text", "vision"])
    assert "one-secret" not in config_revision(base)
    assert config_revision(base) != config_revision(vision)


def test_remote_profiles_are_preferred_for_translation():
    profile = choose_profile(
        [
            {
                "id": "local",
                "name": "Local",
                "endpoint": "http://127.0.0.1:8080/v1/chat/completions",
                "model": "local",
                "source": "managed-local",
                "capabilities": ["text"],
                "languages": ["zh-CN"],
            },
            {
                "id": "remote",
                "name": "Remote",
                "endpoint": "https://api.example.com/v1/chat/completions",
                "model": "remote",
                "source": "remote",
                "capabilities": ["text"],
                "languages": ["zh-CN"],
            },
        ],
        "text",
        language="zh-CN",
    )
    assert profile.id == "remote"


def test_caption_requires_vision_and_can_fallback_to_local():
    profile = choose_profile(
        [
            {
                "id": "remote-text",
                "name": "Remote text",
                "endpoint": "https://api.example.com/v1/chat/completions",
                "model": "text",
                "source": "remote",
                "capabilities": ["text"],
                "languages": ["zh-CN"],
            },
            {
                "id": "local-vision",
                "name": "Qwen3 VL",
                "endpoint": "http://127.0.0.1:8080/v1/chat/completions",
                "model": "qwen3-vl",
                "source": "managed-local",
                "capabilities": ["text", "vision"],
                "languages": ["zh-CN"],
            },
        ],
        "vision",
        language="zh-CN",
    )
    assert profile.id == "local-vision"


def test_text_only_profiles_are_rejected_for_caption():
    with pytest.raises(LLMRouteError, match="vision"):
        choose_profile(
            [
                {
                    "id": "text",
                    "name": "Text",
                    "endpoint": "https://api.example.com/v1/chat/completions",
                    "model": "text",
                    "source": "remote",
                    "capabilities": ["text"],
                    "languages": ["zh-CN"],
                }
            ],
            "vision",
            language="zh-CN",
            allow_local_fallback=False,
        )

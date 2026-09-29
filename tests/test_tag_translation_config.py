from __future__ import annotations

import pytest

from mikazuki.tag_translation.translation_config import mask_config, validate_config


def test_config_supports_local_openai_compatible_endpoint():
    config = validate_config({"deepseek": {"endpoint": "http://127.0.0.1:8000/v1/chat/completions", "model": "Qwen/Qwen3.5-0.8B"}})
    assert config["deepseek"]["endpoint"].startswith("http://127.0.0.1")
    assert config["deepseek"]["model"] == "Qwen/Qwen3.5-0.8B"


def test_config_rejects_non_https_remote_endpoint():
    with pytest.raises(ValueError, match="endpoint"):
        validate_config({"deepseek": {"endpoint": "http://example.invalid/chat/completions"}})


def test_config_rejects_loopback_lookalike():
    with pytest.raises(ValueError, match="endpoint"):
        validate_config({"deepseek": {"endpoint": "http://127.0.0.1.evil.invalid/chat/completions"}})


def test_config_masks_api_key():
    masked = mask_config(validate_config({"deepseek": {"api_key": "secret"}}))
    assert masked["deepseek"]["api_key"] == "********"
    assert masked["deepseek"]["api_key_configured"] is True

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


def test_remote_profiles_keep_one_active_route_and_mask_keys():
    config = validate_config({
        "llm_mode": "remote",
        "active_remote_id": "silicon",
        "remote_profiles": [
            {
                "id": "deepseek",
                "name": "DeepSeek",
                "endpoint": "https://api.deepseek.com/chat/completions",
                "model": "deepseek-v4-flash",
                "api_key": "one",
            },
            {
                "id": "silicon",
                "name": "SiliconFlow",
                "endpoint": "https://api.siliconflow.cn/v1/chat/completions",
                "model": "Qwen/Qwen3.5-35B-A3B",
                "api_key": "two",
            },
        ],
    })
    assert config["deepseek"]["endpoint"] == "https://api.siliconflow.cn/v1/chat/completions"
    assert config["local"]["enabled"] is False
    assert mask_config(config)["remote_profiles"][1]["api_key"] == "********"


def test_local_mode_is_mutually_exclusive():
    config = validate_config({"llm_mode": "local"})
    assert config["local"]["enabled"] is True


def test_masked_profile_key_is_preserved_on_save():
    current = validate_config({
        "remote_profiles": [{
            "id": "one",
            "name": "One",
            "endpoint": "https://example.com/v1/chat/completions",
            "model": "m",
            "api_key": "secret",
        }],
        "active_remote_id": "one",
    })
    saved = validate_config({
        "remote_profiles": [{
            "id": "one",
            "name": "Renamed",
            "endpoint": "https://example.com/v1/chat/completions",
            "model": "m2",
            "api_key": "********",
        }],
        "active_remote_id": "one",
    }, current)
    assert saved["remote_profiles"][0]["api_key"] == "secret"

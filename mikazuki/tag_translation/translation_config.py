# This file is adapted from ComfyUI-Autocomplete-Aaalice.
# Source snapshot: 37cabccf9b4d799b7b53a1e2d74f2cd214fe91d0
# License: MIT; see docs/third_party/comfyui-autocomplete-aaalice-MIT.txt.
# Next Trainer changes are tracked in git history.

import copy
import json
import os
import tempfile
from urllib.parse import urlparse


DEFAULT_SYSTEM_PROMPT = (
    "You are a Danbooru tag translation expert. Translate every supplied tag into the requested language. "
    "Preserve names and established terminology accurately. Return JSON only in the requested schema."
)

DEFAULT_CONFIG = {
    "version": 3,
    "features": {
        "danbooru_completion": True,
        "translation": True,
    },
    "deepseek": {
        "endpoint": "https://api.deepseek.com/chat/completions",
        "api_key": "",
        "model": "deepseek-v4-flash",
        "reasoning_effort": "disabled",
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "concurrency": 4,
        "batch_size": 20,
        "max_retries": 3,
        "timeout_seconds": 180,
    },
    "local": {
        "enabled": False,
        "endpoint": "http://127.0.0.1:8081/v1/chat/completions",
        "runtime_path": "",
        "port": 8081,
        "context_length": 2048,
    },
}

SECRET_MASK = "********"


def validate_config(raw_config, current_config=None):
    """Validate translation settings while discarding retired live-scan fields."""
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, dict):
        raise ValueError("Configuration must be an object")

    config = copy.deepcopy(current_config or DEFAULT_CONFIG)
    config.setdefault("features", copy.deepcopy(DEFAULT_CONFIG["features"]))
    config.setdefault("deepseek", copy.deepcopy(DEFAULT_CONFIG["deepseek"]))
    config.setdefault("local", copy.deepcopy(DEFAULT_CONFIG["local"]))
    config["version"] = DEFAULT_CONFIG["version"]
    raw_features = raw_config.get("features", {})
    if not isinstance(raw_features, dict):
        raise ValueError("features must be an object")
    for key in ("danbooru_completion", "translation"):
        if key not in raw_features:
            continue
        if not isinstance(raw_features[key], bool):
            raise ValueError(f"features.{key} must be a boolean")
        config["features"][key] = raw_features[key]

    raw_deepseek = raw_config.get("deepseek", {})
    if not isinstance(raw_deepseek, dict):
        raise ValueError("deepseek must be an object")

    _apply_secret(config["deepseek"], raw_deepseek, "api_key")
    for key, maximum_length in (("endpoint", 500), ("model", 200), ("system_prompt", 20_000)):
        if key not in raw_deepseek:
            continue
        value = _validate_string(raw_deepseek[key], f"deepseek.{key}", maximum_length).strip()
        if not value:
            raise ValueError(f"deepseek.{key} cannot be empty")
        if key == "endpoint":
            parsed = urlparse(value)
            local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            if not (parsed.scheme == "https" or local_http) or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("deepseek.endpoint must use HTTPS or local loopback HTTP")
            if not parsed.path.endswith("/chat/completions"):
                raise ValueError("deepseek.endpoint must end with /chat/completions")
        config["deepseek"][key] = value

    if "reasoning_effort" in raw_deepseek:
        reasoning_effort = raw_deepseek["reasoning_effort"]
        if reasoning_effort not in {"disabled", "high", "max"}:
            raise ValueError("deepseek.reasoning_effort must be disabled, high, or max")
        config["deepseek"]["reasoning_effort"] = reasoning_effort

    numeric_limits = {
        "concurrency": (1, 300),
        "batch_size": (1, 200),
        "max_retries": (0, 10),
        "timeout_seconds": (10, 600),
    }
    for key, (minimum, maximum) in numeric_limits.items():
        if key not in raw_deepseek:
            continue
        value = raw_deepseek[key]
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"deepseek.{key} must be between {minimum} and {maximum}")
        config["deepseek"][key] = value

    raw_local = raw_config.get("local", {})
    if not isinstance(raw_local, dict):
        raise ValueError("local must be an object")
    if "enabled" in raw_local:
        if not isinstance(raw_local["enabled"], bool):
            raise ValueError("local.enabled must be a boolean")
        config["local"]["enabled"] = raw_local["enabled"]
    for key, maximum_length in (("endpoint", 500), ("runtime_path", 2000)):
        if key not in raw_local:
            continue
        value = _validate_string(raw_local[key], f"local.{key}", maximum_length).strip()
        if key == "endpoint":
            parsed = urlparse(value)
            if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("local.endpoint must use loopback HTTP")
            if not parsed.path.endswith("/chat/completions"):
                raise ValueError("local.endpoint must end with /chat/completions")
        config["local"][key] = value
    for key, (minimum, maximum) in (("port", (1, 65535)), ("context_length", (256, 32768))):
        if key not in raw_local:
            continue
        value = raw_local[key]
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"local.{key} must be between {minimum} and {maximum}")
        config["local"][key] = value
    return config


def local_llm_endpoint(value):
    parsed = urlparse(str(value or ""))
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def mask_config(config):
    masked = copy.deepcopy(config)
    configured = bool(masked["deepseek"].get("api_key"))
    masked["deepseek"]["api_key"] = SECRET_MASK if configured else ""
    masked["deepseek"]["api_key_configured"] = configured
    return masked


class OnlineServiceConfig:
    def __init__(self, path):
        self.path = path

    def load(self):
        if not os.path.exists(self.path):
            return copy.deepcopy(DEFAULT_CONFIG)
        try:
            with open(self.path, encoding="utf-8") as config_file:
                # Version 1 live-tag settings are intentionally reduced to their
                # compatible DeepSeek section on first load/save.
                return validate_config(json.load(config_file))
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise RuntimeError(f"Unable to load translation configuration: {error}") from error

    def save(self, raw_config):
        config = validate_config(raw_config, self.load())
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        file_descriptor, temp_path = tempfile.mkstemp(
            prefix="translation-config-",
            suffix=".json.tmp",
            dir=os.path.dirname(self.path),
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as config_file:
                json.dump(config, config_file, ensure_ascii=False, indent=2)
                config_file.write("\n")
            os.replace(temp_path, self.path)
            os.chmod(self.path, 0o600)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
        return config


def _validate_string(value, name, maximum_length):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    if len(value) > maximum_length:
        raise ValueError(f"{name} is too long")
    return value


def _apply_secret(target, raw_section, key):
    if key not in raw_section:
        return
    value = _validate_string(raw_section[key], f"deepseek.{key}", 1000)
    if value != SECRET_MASK:
        target[key] = value.strip()

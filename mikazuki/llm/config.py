from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

from .contracts import LLMCapability, LLMContractError, LLMProfile, LLMSource
from .secrets import read_configuration, write_configuration

CURRENT_CONFIG_VERSION = 5
SECRET_MASK = "********"
_ALLOWED_SOURCES = {"remote", "local-endpoint", "managed-local"}
_ALLOWED_CAPABILITIES = {"text", "vision"}
_CONFIG_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def configuration_lock(path):
    key = os.path.normcase(str(Path(path).resolve()))
    with _LOCKS_GUARD:
        return _CONFIG_LOCKS.setdefault(key, threading.RLock())


def _string(value, name: str, limit: int) -> str:
    if not isinstance(value, str):
        raise LLMContractError(f"{name} must be a string")
    value = value.strip()
    if len(value) > limit:
        raise LLMContractError(f"{name} is too long")
    return value


def _validate_endpoint(value: str) -> str:
    try:
        parsed = urlparse(value)
        valid_host = bool(parsed.hostname) and (parsed.port is None or 1 <= parsed.port <= 65535)
    except ValueError:
        valid_host = False
    if not valid_host:
        raise LLMContractError("endpoint requires a valid host and port")
    loopback = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if not (parsed.scheme == "https" or loopback):
        raise LLMContractError("endpoint must use HTTPS or loopback HTTP")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LLMContractError("endpoint must not contain credentials, query, or fragment")
    if not parsed.path.endswith("/chat/completions"):
        raise LLMContractError("endpoint must end with /chat/completions")
    return value


def validate_profile(raw: dict, previous: dict | None = None) -> dict:
    if not isinstance(raw, dict):
        raise LLMContractError("profile must be an object")
    profile_id = _string(raw.get("id", ""), "profile.id", 80)
    name = _string(raw.get("name", profile_id), "profile.name", 120)
    endpoint = _validate_endpoint(_string(raw.get("endpoint", ""), "profile.endpoint", 500))
    model = _string(raw.get("model", ""), "profile.model", 200)
    if not profile_id or not name or not model:
        raise LLMContractError("profile id, name and model are required")
    source = raw.get("source", "remote")
    if source not in _ALLOWED_SOURCES:
        raise LLMContractError("profile.source is invalid")
    raw_capabilities = raw.get("capabilities", ["text"])
    if not isinstance(raw_capabilities, (list, tuple)) or any(not isinstance(item, str) for item in raw_capabilities):
        raise LLMContractError("profile.capabilities must be an array of strings")
    capabilities = tuple(dict.fromkeys(raw_capabilities))
    if not capabilities or any(item not in _ALLOWED_CAPABILITIES for item in capabilities):
        raise LLMContractError("profile.capabilities is invalid")
    raw_languages = raw.get("languages", ["en"])
    if not isinstance(raw_languages, (list, tuple)) or any(not isinstance(item, str) for item in raw_languages):
        raise LLMContractError("profile.languages must be an array of strings")
    languages = tuple(dict.fromkeys(raw_languages))
    if not languages or len(languages) > 32 or any(item != "*" and not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", item) for item in languages):
        raise LLMContractError("profile.languages is invalid")
    api_key = _string(raw.get("api_key", previous.get("api_key", "") if previous else ""), "profile.api_key", 1000)
    if api_key == SECRET_MASK and previous:
        api_key = str(previous.get("api_key", ""))
    elif api_key == SECRET_MASK:
        raise LLMContractError("a masked API key requires an existing profile")
    asset_id = raw.get("asset_id")
    if asset_id is not None:
        asset_id = _string(asset_id, "profile.asset_id", 200)
    revision = raw.get("revision")
    if revision is not None:
        revision = _string(revision, "profile.revision", 200)
    for flag in ("enabled", "ready"):
        if flag in raw and not isinstance(raw[flag], bool):
            raise LLMContractError(f"profile.{flag} must be a boolean")
    secret_revision = (previous or raw).get("secret_revision", 0)
    if isinstance(secret_revision, bool) or not isinstance(secret_revision, int) or secret_revision < 0:
        raise LLMContractError("profile.secret_revision must be a non-negative integer")
    metadata = raw.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise LLMContractError("profile.metadata must be an object")
    if previous and api_key != previous.get("api_key", ""):
        secret_revision += 1
    return {
        "id": profile_id,
        "name": name,
        "endpoint": endpoint,
        "model": model,
        "source": source,
        "capabilities": list(capabilities),
        "languages": list(languages),
        "api_key": api_key,
        "asset_id": asset_id,
        "revision": revision,
        "enabled": bool(raw.get("enabled", True)),
        "ready": bool(raw.get("ready", True)),
        "metadata": copy.deepcopy(metadata),
        "secret_revision": secret_revision,
    }


def _profile_from_legacy(section: dict, profile_id: str, source: LLMSource = "remote") -> dict:
    return {
        "id": profile_id,
        "name": section.get("name") or "默认远程接口",
        "endpoint": section["endpoint"],
        "model": section["model"],
        "source": source,
        "capabilities": ["text"],
        "languages": ["en", "zh", "zh-CN", "zh-TW", "ja"],
        "api_key": section.get("api_key", ""),
        "enabled": True,
        "ready": True,
        "metadata": {"migrated_from": "tag_translation.v4"},
    }


def migrate_legacy_translation_config(raw: dict | None) -> dict:
    """Convert v4 translation settings to a unified v5 profile document.

    The function is pure and does not write files. Existing callers can keep
    their v4 persistence until the shared facade is wired in.
    """
    raw = copy.deepcopy(raw or {})
    if not isinstance(raw, dict):
        raise LLMContractError("configuration must be an object")
    if raw.get("version") == CURRENT_CONFIG_VERSION and isinstance(raw.get("profiles"), list):
        profiles = [validate_profile(item) for item in raw["profiles"]]
        return {
            "version": CURRENT_CONFIG_VERSION,
            "profiles": profiles,
            "routes": dict(raw.get("routes") or {}),
            "prompt_presets": copy.deepcopy(raw.get("prompt_presets") or []),
            "cache": copy.deepcopy(raw.get("cache") or {"translation": True, "caption": True}),
        }

    profiles: list[dict] = []
    legacy_profiles = raw.get("remote_profiles") or []
    previous = {item.get("id"): item for item in legacy_profiles if isinstance(item, dict)}
    for item in legacy_profiles:
        profiles.append(validate_profile(_profile_from_legacy(item, item.get("id", "remote-default")), previous.get(item.get("id"))))
    if not profiles:
        deepseek = raw.get("deepseek") or {}
        if deepseek:
            profiles.append(validate_profile(_profile_from_legacy(deepseek, "remote-default")))
    if not profiles:
        raise LLMContractError("legacy configuration has no usable remote profile")

    active_remote = raw.get("active_remote_id") or profiles[0]["id"]
    if not any(profile["id"] == active_remote for profile in profiles):
        active_remote = profiles[0]["id"]
    local = raw.get("local") or {}
    local_endpoint = local.get("endpoint")
    if local.get("enabled") and isinstance(local_endpoint, str) and local_endpoint.startswith("http"):
        local_profile = validate_profile(
            {
                "id": "managed-local-legacy",
                "name": "迁移的本地接口",
                "endpoint": local_endpoint,
                "model": local.get("model") or "local",
                "source": "managed-local",
                "capabilities": ["text"],
                "languages": ["en", "zh", "zh-CN", "zh-TW", "ja"],
                "asset_id": "legacy-local",
            }
        )
        profiles.append(local_profile)

    return {
        "version": CURRENT_CONFIG_VERSION,
        "profiles": profiles,
        "routes": {"translation": active_remote, "caption": active_remote},
        "prompt_presets": [],
        "cache": {"translation": True, "caption": True},
    }


def mask_profiles(config: dict) -> dict:
    masked = copy.deepcopy(config)
    for profile in masked.get("profiles", []):
        configured = bool(profile.get("api_key"))
        profile["api_key"] = SECRET_MASK if configured else ""
        profile["api_key_configured"] = configured
    return masked


def validate_options(config: dict) -> None:
    routes = config.get("routes", {})
    if not isinstance(routes, dict) or any(key not in {"translation", "caption"} or not isinstance(value, str) for key, value in routes.items()):
        raise LLMContractError("routes must map translation or caption to a profile id")
    cache = config.get("cache")
    if not isinstance(cache, dict) or any(key not in {"caption", "translation"} or not isinstance(value, bool) for key, value in cache.items()):
        raise LLMContractError("cache must contain boolean caption and translation flags")
    presets = config.get("prompt_presets")
    if not isinstance(presets, list) or len(presets) > 24:
        raise LLMContractError("prompt_presets must be an array of at most 24 presets")
    seen = set()
    for preset in presets:
        if not isinstance(preset, dict) or set(preset) - {"id", "name", "template", "language"}:
            raise LLMContractError("prompt preset has invalid fields")
        identifier = _string(preset.get("id", ""), "prompt.id", 80)
        name = _string(preset.get("name", ""), "prompt.name", 120)
        template = _string(preset.get("template", ""), "prompt.template", 8000)
        if not identifier or identifier in seen or not name or not template:
            raise LLMContractError("prompt preset requires a unique id, name and template")
        if preset.get("language") not in {"zh-CN", "zh-TW", "en", "ja"}:
            raise LLMContractError("prompt preset language is unsupported")
        variables = re.findall(r"\{\{([^{}]*)\}\}", template)
        if any(variable not in {"language", "mode", "image_name", "existing_caption", "existing_tags"} for variable in variables):
            raise LLMContractError("prompt preset contains an unknown variable")
        seen.add(identifier)


def config_revision(profile: dict | LLMProfile, prompt_revision: str | None = None) -> str:
    if isinstance(profile, LLMProfile):
        data = {
            "id": profile.id,
            "endpoint": profile.endpoint,
            "model": profile.model,
            "source": profile.source,
            "capabilities": profile.capabilities,
            "languages": profile.languages,
            "asset_id": profile.asset_id,
            "revision": profile.revision,
            "secret_revision": profile.metadata.get("secret_revision", 0),
        }
    else:
        data = {
            key: profile.get(key)
            for key in ("id", "endpoint", "model", "source", "capabilities", "languages", "asset_id", "revision", "secret_revision")
        }
    data["prompt_revision"] = prompt_revision
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]


class UnifiedConfigStore:
    """Persist the shared LLM document beside the legacy translation config."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)

    def _read_document(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            payload = read_configuration(self.path)
        except (OSError, json.JSONDecodeError) as exc:
            raise LLMContractError("shared LLM configuration is unreadable") from exc
        if not isinstance(payload, dict):
            raise LLMContractError("shared LLM configuration must be an object")
        return payload

    def load(self) -> dict:
        document = self._read_document()
        raw = document.get("llm")
        if isinstance(raw, dict):
            if not isinstance(raw.get("profiles"), list) or len(raw["profiles"]) > 24 or any(not isinstance(item, dict) for item in raw["profiles"]):
                raise LLMContractError("stored profiles must be an array of at most 24 objects")
            profiles = [
                validate_profile(item, None)
                for item in raw.get("profiles", [])
                if isinstance(item, dict)
            ]
            if len({profile["id"] for profile in profiles}) != len(profiles):
                raise LLMContractError("stored profile ids must be unique")
            if isinstance(raw.get("profiles"), list):
                config = {
                    "version": CURRENT_CONFIG_VERSION,
                    "profiles": profiles,
                    "routes": copy.deepcopy(raw.get("routes", {})),
                    "prompt_presets": copy.deepcopy(raw.get("prompt_presets", [])),
                    "cache": copy.deepcopy(raw.get("cache", {"translation": True, "caption": True})),
                }
                validate_options(config)
                return config
        if not document:
            return {
                "version": CURRENT_CONFIG_VERSION,
                "profiles": [],
                "routes": {},
                "prompt_presets": [],
                "cache": {"translation": True, "caption": True},
            }
        return migrate_legacy_translation_config(document)

    def load_masked(self) -> dict:
        return mask_profiles(self.load())

    def save(self, payload: dict) -> dict:
        with configuration_lock(self.path):
            return self._save(payload)

    def _save(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise LLMContractError("shared LLM configuration must be an object")
        current = self.load()
        previous = {item["id"]: item for item in current.get("profiles", [])}
        raw_profiles = payload.get("profiles", current.get("profiles", []))
        if not isinstance(raw_profiles, list) or len(raw_profiles) > 24:
            raise LLMContractError("profiles must contain at most 24 profiles")
        if any(not isinstance(item, dict) for item in raw_profiles):
            raise LLMContractError("each profile must be an object")
        profiles = [validate_profile(item, previous.get(str(item.get("id")))) for item in raw_profiles]
        ids = {profile["id"] for profile in profiles}
        if len(ids) != len(profiles):
            raise LLMContractError("profile ids must be unique")
        raw_routes = payload.get("routes", {})
        if not isinstance(raw_routes, dict) or any(key not in {"translation", "caption"} or not isinstance(value, str) for key, value in raw_routes.items()):
            raise LLMContractError("routes must map translation or caption to a profile id")
        routes = dict(current.get("routes") or {})
        routes.update(raw_routes)
        remote_ids = [profile["id"] for profile in profiles if profile["source"] == "remote"]
        for route_name in ("translation", "caption"):
            if not profiles:
                routes.pop(route_name, None)
                continue
            selected = routes.get(route_name)
            if selected not in ids:
                routes[route_name] = remote_ids[0] if remote_ids else profiles[0]["id"]
        config = {
            "version": CURRENT_CONFIG_VERSION,
            "profiles": profiles,
            "routes": routes,
            "prompt_presets": copy.deepcopy(payload.get("prompt_presets", current.get("prompt_presets", []))),
            "cache": copy.deepcopy(payload.get("cache", current.get("cache", {"translation": True, "caption": True}))),
        }
        validate_options(config)
        document = self._read_document()
        document["llm"] = config
        self._sync_legacy_translation_fields(document, profiles, routes)
        write_configuration(self.path, document)
        return config

    @staticmethod
    def _sync_legacy_translation_fields(document: dict, profiles: list[dict], routes: dict) -> None:
        from mikazuki.tag_translation.translation_config import DEFAULT_CONFIG
        previous = {profile["id"]: profile for profile in document.get("remote_profiles", [])}
        remotes = [profile for profile in profiles if profile["source"] == "remote"]
        selected_id = routes.get("translation")
        selected = next((profile for profile in remotes if profile["id"] == selected_id), None)
        if selected is None and remotes:
            selected = remotes[0]
            routes["translation"] = selected["id"]
        if selected is None:
            if not remotes:
                document["remote_profiles"] = copy.deepcopy(DEFAULT_CONFIG["remote_profiles"])
                document["active_remote_id"] = DEFAULT_CONFIG["active_remote_id"]
                document["deepseek"] = copy.deepcopy(DEFAULT_CONFIG["deepseek"])
            return
        document["version"] = 4
        document["active_remote_id"] = selected["id"]
        document["remote_profiles"] = [
            {
                "id": profile["id"],
                "name": profile["name"],
                "endpoint": profile["endpoint"],
                "api_key": profile.get("api_key", ""),
                "model": profile["model"],
                "reasoning_effort": "disabled",
                "system_prompt": previous.get(profile["id"], {}).get("system_prompt", DEFAULT_CONFIG["deepseek"]["system_prompt"]),
            }
            for profile in remotes
        ]
        document["deepseek"] = {
            **copy.deepcopy(DEFAULT_CONFIG["deepseek"]),
            **document.get("deepseek", {}),
            "endpoint": selected["endpoint"],
            "api_key": selected.get("api_key", ""),
            "model": selected["model"],
            "reasoning_effort": "disabled",
            "system_prompt": previous.get(selected["id"], {}).get("system_prompt", document.get("deepseek", {}).get("system_prompt", DEFAULT_CONFIG["deepseek"]["system_prompt"])),
        }

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from .contracts import LLMCapability, LLMContractError, LLMProfile, LLMSource

CURRENT_CONFIG_VERSION = 5
SECRET_MASK = "********"
_ALLOWED_SOURCES = {"remote", "local-endpoint", "managed-local"}
_ALLOWED_CAPABILITIES = {"text", "vision"}


def _string(value, name: str, limit: int) -> str:
    if not isinstance(value, str):
        raise LLMContractError(f"{name} must be a string")
    value = value.strip()
    if len(value) > limit:
        raise LLMContractError(f"{name} is too long")
    return value


def _validate_endpoint(value: str) -> str:
    parsed = urlparse(value)
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
    source = raw.get("source", "remote")
    if source not in _ALLOWED_SOURCES:
        raise LLMContractError("profile.source is invalid")
    capabilities = tuple(dict.fromkeys(raw.get("capabilities", ["text"])))
    if not capabilities or any(item not in _ALLOWED_CAPABILITIES for item in capabilities):
        raise LLMContractError("profile.capabilities is invalid")
    languages = tuple(dict.fromkeys(raw.get("languages", ["en"])))
    if not languages or any(not isinstance(item, str) or not item.strip() for item in languages):
        raise LLMContractError("profile.languages is invalid")
    api_key = _string(raw.get("api_key", ""), "profile.api_key", 1000)
    if api_key == SECRET_MASK and previous:
        api_key = str(previous.get("api_key", ""))
    asset_id = raw.get("asset_id")
    if asset_id is not None:
        asset_id = _string(asset_id, "profile.asset_id", 200)
    revision = raw.get("revision")
    if revision is not None:
        revision = _string(revision, "profile.revision", 200)
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
        "metadata": copy.deepcopy(raw.get("metadata") or {}),
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
        }
    else:
        data = {
            key: profile.get(key)
            for key in ("id", "endpoint", "model", "source", "capabilities", "languages", "asset_id", "revision")
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
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LLMContractError("shared LLM configuration is unreadable") from exc
        if not isinstance(payload, dict):
            raise LLMContractError("shared LLM configuration must be an object")
        return payload

    def load(self) -> dict:
        document = self._read_document()
        raw = document.get("llm")
        if isinstance(raw, dict):
            profiles = [
                validate_profile(item, None)
                for item in raw.get("profiles", [])
                if isinstance(item, dict)
            ]
            if profiles:
                return {
                    "version": CURRENT_CONFIG_VERSION,
                    "profiles": profiles,
                    "routes": dict(raw.get("routes") or {}),
                    "prompt_presets": copy.deepcopy(raw.get("prompt_presets") or []),
                    "cache": copy.deepcopy(raw.get("cache") or {"translation": True, "caption": True}),
                }
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
        if not isinstance(payload, dict):
            raise LLMContractError("shared LLM configuration must be an object")
        current = self.load()
        previous = {item["id"]: item for item in current.get("profiles", [])}
        raw_profiles = payload.get("profiles", current.get("profiles", []))
        if not isinstance(raw_profiles, list) or not raw_profiles:
            raise LLMContractError("profiles must contain at least one profile")
        profiles = [validate_profile(item, previous.get(str(item.get("id")))) for item in raw_profiles]
        ids = {profile["id"] for profile in profiles}
        routes = dict(current.get("routes") or {})
        routes.update(dict(payload.get("routes") or {}))
        remote_ids = [profile["id"] for profile in profiles if profile["source"] == "remote"]
        for route_name in ("translation", "caption"):
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
        document = self._read_document()
        document["llm"] = config
        self._sync_legacy_translation_fields(document, profiles, routes)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="llm-config-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as target:
                json.dump(document, target, ensure_ascii=False, indent=2)
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        return config

    @staticmethod
    def _sync_legacy_translation_fields(document: dict, profiles: list[dict], routes: dict) -> None:
        remotes = [profile for profile in profiles if profile["source"] == "remote"]
        selected_id = routes.get("translation")
        selected = next((profile for profile in remotes if profile["id"] == selected_id), None)
        if selected is None and remotes:
            selected = remotes[0]
            routes["translation"] = selected["id"]
        if selected is None:
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
                "system_prompt": "You are a tag translation assistant.",
            }
            for profile in remotes
        ]
        document["deepseek"] = {
            "endpoint": selected["endpoint"],
            "api_key": selected.get("api_key", ""),
            "model": selected["model"],
            "reasoning_effort": "disabled",
            "system_prompt": "You are a tag translation assistant.",
            "concurrency": 4,
            "batch_size": 20,
            "max_retries": 3,
            "timeout_seconds": 180,
        }

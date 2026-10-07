from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from .config import LLMContractError

_LANGUAGES = {"zh-CN", "zh-TW", "en", "ja"}
_KINDS = {"caption_prompt"}
_LOCK = threading.RLock()


def user_data_root() -> Path:
    configured = os.environ.get("MIKAZUKI_USER_DATA_ROOT", "").strip()
    root = Path(__file__).resolve().parents[2]
    path = Path(configured).expanduser() if configured else Path("user_data")
    return path if path.is_absolute() else root / path


def presets_dir() -> Path:
    return user_data_root() / "presets"


def settings_path() -> Path:
    return user_data_root() / "settings.json"


def _text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise LLMContractError(f"{field} must be a string")
    value = value.strip()
    if not value or len(value) > limit:
        raise LLMContractError(f"{field} is invalid")
    return value


def validate_preset(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise LLMContractError("caption preset must be an object")
    allowed = {"schema_version", "id", "kind", "name", "template", "system_prompt", "output_format", "language", "max_length", "model_capabilities", "revision"}
    if set(raw) - allowed:
        raise LLMContractError("caption preset contains unknown fields")
    if raw.get("schema_version", 1) != 1:
        raise LLMContractError("caption preset schema_version is unsupported")
    identifier = _text(raw.get("id"), "preset.id", 80)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier):
        raise LLMContractError("preset.id is invalid")
    kind = raw.get("kind", "caption_prompt")
    if not isinstance(kind, str) or kind not in _KINDS:
        raise LLMContractError("preset.kind is invalid")
    name = _text(raw.get("name"), "preset.name", 120)
    template = _text(raw.get("template"), "preset.template", 8000)
    system_prompt = raw.get("system_prompt", "")
    if not isinstance(system_prompt, str):
        raise LLMContractError("preset.system_prompt must be a string")
    system_prompt = system_prompt.strip()
    if len(system_prompt) > 8000:
        raise LLMContractError("preset.system_prompt is too long")
    language = raw.get("language", "zh-CN")
    if not isinstance(language, str) or language not in _LANGUAGES:
        raise LLMContractError("preset.language is unsupported")
    output_format = raw.get("output_format", "plain_text")
    if output_format != "plain_text":
        raise LLMContractError("preset.output_format is unsupported")
    maximum = raw.get("max_length", 2000)
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 2000:
        raise LLMContractError("preset.max_length must be between 1 and 2000")
    capabilities = raw.get("model_capabilities", ["vision", "caption"])
    if not isinstance(capabilities, list) or any(not isinstance(item, str) or item not in {"vision", "caption"} for item in capabilities) or "vision" not in capabilities:
        raise LLMContractError("preset.model_capabilities must include vision")
    variables = re.findall(r"\{\{([^{}]*)\}\}", template)
    if any(variable not in {"language", "mode", "image_name", "existing_caption", "existing_tags"} for variable in variables):
        raise LLMContractError("preset.template contains an unknown variable")
    revision = hashlib.sha256(json.dumps({"kind": kind, "template": template, "system_prompt": system_prompt, "language": language, "max_length": maximum, "output_format": output_format, "model_capabilities": capabilities}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return {"schema_version": 1, "id": identifier, "kind": kind, "name": name, "template": template, "system_prompt": system_prompt, "output_format": output_format, "language": language, "max_length": maximum, "model_capabilities": list(dict.fromkeys(capabilities)), "revision": revision}


def _read_json(path: Path, default: Any) -> Any:
    if path.is_symlink() or path.parent.is_symlink():
        raise LLMContractError("user data cannot use symbolic links")
    if not path.is_file():
        return copy.deepcopy(default)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LLMContractError(f"user data is unreadable: {path.name}") from exc
    return value


def list_presets() -> list[dict[str, Any]]:
    with _LOCK:
        directory = presets_dir()
        if not directory.is_dir():
            return []
        result = []
        for path in sorted(directory.glob("*.json")):
            raw = _read_json(path, {})
            if isinstance(raw, dict) and raw.get("kind") == "caption_prompt":
                result.append(validate_preset(raw))
        return result


def document_revision() -> str:
    return hashlib.sha256(json.dumps({"presets": list_presets(), "settings": settings()}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def _write_json(target: Path, payload: dict) -> None:
    _read_json(target, {})  # Validate existing data before replacing or backing it up.
    if target.is_file():
        backup = target.with_suffix(".json.bak")
        if backup.is_symlink():
            raise LLMContractError("user data backup cannot use symbolic links")
        backup.write_bytes(target.read_bytes())
    temporary = target.with_suffix(".json.tmp")
    if temporary.is_symlink():
        raise LLMContractError("user data temporary file cannot use symbolic links")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)


def save_presets(items: list[dict[str, Any]], *, expected_revision: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(items, list) or len(items) > 24:
        raise LLMContractError("caption presets must be an array of at most 24 objects")
    validated = [validate_preset(item) for item in items]
    if len({item["id"].casefold() for item in validated}) != len(validated):
        raise LLMContractError("caption preset ids must be unique")
    with _LOCK:
        if expected_revision is not None and expected_revision != document_revision():
            raise LLMContractError("caption preset revision conflict")
        directory = presets_dir()
        if directory.is_symlink() or user_data_root().is_symlink():
            raise LLMContractError("user data cannot use symbolic links")
        directory.mkdir(parents=True, exist_ok=True)
        wanted = {item["id"] for item in validated}
        existing = {}
        for path in directory.glob("*.json"):
            raw = _read_json(path, {})
            existing[path.stem] = raw
            if path.stem in wanted and (not isinstance(raw, dict) or raw.get("kind") != "caption_prompt"):
                raise LLMContractError("caption preset id collides with another preset type")
        for item in validated:
            target = directory / f"{item['id']}.json"
            _write_json(target, item)
        for identifier, raw in existing.items():
            if identifier not in wanted and isinstance(raw, dict) and raw.get("kind") == "caption_prompt":
                path = directory / f"{identifier}.json"
                _write_json(path, validate_preset(raw))
                path.unlink()
        return validated


def settings() -> dict[str, Any]:
    with _LOCK:
        value = _read_json(settings_path(), {})
        if not isinstance(value, dict):
            raise LLMContractError("user settings must be an object")
        return {"default_caption_preset_id": value.get("default_caption_preset_id") or None}


def document() -> dict:
    with _LOCK:
        return {"presets": list_presets(), "settings": settings(), "revision": document_revision()}


def save_settings(default_caption_preset_id: str | None) -> dict[str, Any]:
    if default_caption_preset_id is not None:
        default_caption_preset_id = _text(default_caption_preset_id, "default_caption_preset_id", 80)
        if default_caption_preset_id not in {item["id"] for item in list_presets()}:
            raise LLMContractError("default caption preset does not exist")
    with _LOCK:
        root = user_data_root()
        root.mkdir(parents=True, exist_ok=True)
        target = settings_path()
        value = _read_json(target, {})
        if not isinstance(value, dict):
            raise LLMContractError("user settings must be an object")
        value.setdefault("schema_version", 1)
        value["default_caption_preset_id"] = default_caption_preset_id
        _write_json(target, value)
        return settings()


def save_document(payload: dict) -> dict:
    with _LOCK:
        if not isinstance(payload, dict) or set(payload) - {"presets", "settings", "revision"}:
            raise LLMContractError("caption preset document is invalid")
        if payload.get("revision") != document_revision():
            raise LLMContractError("caption preset revision conflict")
        items = payload.get("presets")
        if not isinstance(items, list):
            raise LLMContractError("caption presets must be an array")
        validated = [validate_preset(item) for item in items]
        options = payload.get("settings", {})
        if not isinstance(options, dict) or set(options) - {"default_caption_preset_id"}:
            raise LLMContractError("caption preset settings are invalid")
        default_id = options.get("default_caption_preset_id")
        if default_id is not None and default_id not in {item["id"] for item in validated}:
            raise LLMContractError("default caption preset does not exist")
        # Settings validation must precede any preset mutation.
        existing_settings = _read_json(settings_path(), {})
        if not isinstance(existing_settings, dict):
            raise LLMContractError("user settings must be an object")
        saved = save_presets(items)
        options = save_settings(default_id)
        return {"presets": saved, "settings": options, "revision": document_revision()}


def import_legacy(items: list[dict], *, expected_revision: str) -> dict:
    """Explicit import only; existing user ids win and originals stay intact."""
    current = {item["id"]: item for item in list_presets()}
    for item in items:
        migrated = validate_preset({**{key: value for key, value in item.items() if key != "revision"}, "kind": "caption_prompt"})
        current.setdefault(migrated["id"], migrated)
    return save_document({"presets": list(current.values()), "settings": settings(), "revision": expected_revision})

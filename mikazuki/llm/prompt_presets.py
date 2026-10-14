from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .config import LLMContractError
from mikazuki import user_data_transactions as tx

_LANGUAGES = {"zh-CN", "zh-TW", "en", "ja"}
_KINDS = {"caption_prompt"}
_JOURNAL = tx.JOURNAL
CAPTION_TYPE = "tagger-caption"


def user_data_root() -> Path:
    return tx.resolve_root()


def at_root(root):
    return tx.at_root(root)


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
    allowed = {"schema_version", "id", "kind", "name", "template", "system_prompt", "output_format", "language", "max_length", "model_capabilities", "revision", "train_type", "description", "created_at", "updated_at", "builtin_id"}
    if set(raw) - allowed:
        raise LLMContractError("caption preset contains unknown fields")
    if type(raw.get("schema_version", 1)) is not int or raw.get("schema_version", 1) != 1:
        raise LLMContractError("caption preset schema_version is unsupported")
    identifier = _text(raw.get("id"), "preset.id", 80)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier):
        raise LLMContractError("preset.id is invalid")
    if identifier.endswith(".") or identifier.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise LLMContractError("preset.id is not portable")
    kind = raw.get("kind", "caption_prompt")
    if not isinstance(kind, str) or kind not in _KINDS:
        raise LLMContractError("preset.kind is invalid")
    if raw.get("train_type", CAPTION_TYPE) != CAPTION_TYPE:
        raise LLMContractError("caption preset train_type is immutable")
    name = _text(raw.get("name"), "preset.name", 120)
    template = _text(raw.get("template"), "preset.template", 8000)
    system_prompt = raw.get("system_prompt", "")
    if not isinstance(system_prompt, str):
        raise LLMContractError("preset.system_prompt must be a string")
    system_prompt = system_prompt.strip()
    if len(system_prompt) > 8000:
        raise LLMContractError("preset.system_prompt is too long")
    language = raw.get("language", "en")
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
    capabilities = sorted(set(capabilities))
    variables = re.findall(r"\{\{([^{}]*)\}\}", template + system_prompt)
    if any(variable not in {"language", "mode", "image_name", "existing_caption", "existing_tags"} for variable in variables):
        raise LLMContractError("preset.template contains an unknown variable")
    revision = hashlib.sha256(json.dumps({"kind": kind, "template": template, "system_prompt": system_prompt, "language": language, "max_length": maximum, "output_format": output_format, "model_capabilities": capabilities}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    result = {"schema_version": 1, "id": identifier, "kind": kind, "train_type": CAPTION_TYPE, "name": name, "template": template, "system_prompt": system_prompt, "output_format": output_format, "language": language, "max_length": maximum, "model_capabilities": list(dict.fromkeys(capabilities)), "revision": revision}
    for field in ("description", "created_at", "updated_at"):
        if field in raw:
            value = raw[field]
            if not isinstance(value, str) or len(value) > 2000:
                raise LLMContractError(f"preset.{field} is invalid")
            result[field] = value
    if "builtin_id" in raw:
        builtin = raw["builtin_id"]
        # Only an explicitly declared builtin identity is projected. Display names
        # never confer builtin status or permit replacing a user's prompt.
        if builtin is not None and builtin not in {"builtin-caption-en", "builtin-caption-zh", "builtin-caption-en-concise", "builtin-caption-en-detailed"}:
            raise LLMContractError("preset.builtin_id is invalid")
        result["builtin_id"] = builtin
    tx.json_bytes(result)
    return result


def _check_path(path):
    tx.check_path(path)


def _read_json(path, default):
    return tx.read_json(path, default)


def _bytes(path):
    return tx.read_bytes(path)


def _json_bytes(value):
    return tx.json_bytes(value)


def _atomic_bytes(path, value):
    tx.atomic_bytes(path, value)


def _recover():
    tx.recover(_atomic_bytes)


@contextmanager
def _store_guard():
    try:
        with tx.guard(write=_atomic_bytes):
            yield
    except tx.TransactionError as exc:
        raise LLMContractError(str(exc)) from exc


def _transaction(changes):
    tx.transaction(changes, _atomic_bytes)


def is_caption(raw):
    return isinstance(raw, dict) and (raw.get("kind") == "caption_prompt" or raw.get("train_type") == CAPTION_TYPE)


def from_envelope(raw):
    if raw.get("kind") == "caption_prompt":
        return validate_preset(raw)
    if raw.get("train_type") != CAPTION_TYPE or not isinstance(raw.get("config"), dict):
        raise LLMContractError("caption preset envelope is invalid")
    config = copy.deepcopy(raw["config"])
    template = config.pop("prompt", None)
    if template is None:
        template = config.pop("template", None)
    elif "template" in config and config.pop("template") != template:
        raise LLMContractError("caption prompt and template disagree")
    # Dev's old envelope exposes only prompt. Keep its original template and
    # explicitly carry the generation metadata rather than silently dropping it.
    result = {**config, "id": raw.get("id"), "name": raw.get("name"),
              "kind": "caption_prompt", "train_type": CAPTION_TYPE, "template": template}
    for key in ("description", "created_at", "updated_at"):
        if key in raw:
            result[key] = raw[key]
    return validate_preset(result)


def to_envelope(item):
    item = validate_preset(item)
    config = {key: copy.deepcopy(value) for key, value in item.items()
              if key not in {"id", "name", "kind", "train_type", "template", "description", "created_at", "updated_at"}}
    config["prompt"] = item["template"]
    result = {"id": item["id"], "name": item["name"], "train_type": CAPTION_TYPE, "config": config}
    for key in ("description", "created_at", "updated_at"):
        if key in item:
            result[key] = item[key]
    return result


def _records():
    directory = presets_dir()
    _check_path(directory)
    return [(path, _read_json(path, {})) for path in sorted(directory.glob("*.json"))] if directory.is_dir() else []


def list_presets():
    with _store_guard():
        result = [from_envelope(raw) for _path, raw in _records() if is_caption(raw)]
        if len({item["id"].casefold() for item in result}) != len(result):
            raise LLMContractError("caption preset ids must be unique")
        return result


def document_revision():
    with _store_guard():
        # Raw legacy envelopes are part of CAS as well: projection alone must
        # not conceal an external edit before confirmed migration.
        value = {"presets": list_presets(), "settings": _read_json(settings_path(), {}),
                 "sources": {path.name: raw for path, raw in _records() if is_caption(raw)}}
        return _hash(value)[:24]


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()


def _validate_items(items) -> list[dict]:
    if not isinstance(items, list) or len(items) > 24:
        raise LLMContractError("caption presets must be an array of at most 24 objects")
    validated = [validate_preset(item) for item in items]
    if len({item["id"].casefold() for item in validated}) != len(validated):
        raise LLMContractError("caption preset ids must be unique")
    return validated


def _preset_changes(validated, *, migrating=False):
    wanted = {item["id"].casefold(): item for item in validated}
    changes = {}
    for path, raw in _records():
        existing_id = path.stem.casefold()
        if existing_id in wanted and (not is_caption(raw) or path.stem != wanted[existing_id]["id"]):
            raise LLMContractError("caption preset id collides with another preset type or spelling")
        if is_caption(raw):
            from_envelope(raw)
            if (raw.get("kind") != "caption_prompt" or raw.get("train_type") != CAPTION_TYPE) and not migrating:
                raise LLMContractError("legacy caption preset requires explicit import preview and confirmation")
            changes[path.with_suffix(".json.bak")] = _bytes(path)
            if existing_id not in wanted:
                changes[path] = None
    for item in validated:
        changes[presets_dir() / f"{item['id']}.json"] = _json_bytes(item)
    return changes


def _settings_raw():
    value = _read_json(settings_path(), {"schema_version": 1, "revision": 0})
    if not isinstance(value, dict):
        raise LLMContractError("user settings must be an object")
    if type(value.get("revision", 0)) is not int or value.get("revision", 0) < 0:
        raise LLMContractError("user settings revision is invalid")
    return value


def settings():
    with _store_guard():
        value = _settings_raw()
        state = value.get("caption_presets", {})
        defaults = value.get("default_presets", {})
        return {"default_caption_preset_id": defaults.get(CAPTION_TYPE, value.get("default_caption_preset_id")) or None,
                "legacy_imported": bool(state.get("imports")) or value.get("caption_legacy_imported") is True}


def document():
    with _store_guard():
        return {"presets": list_presets(), "settings": settings(), "revision": document_revision()}


def _save(validated, default_id, *, imports=None, migrating=False):
    if default_id is not None and default_id not in {item["id"] for item in validated}:
        raise LLMContractError("default caption preset does not exist")
    value = _settings_raw()
    if not isinstance(value.get("default_presets", {}), dict) or not isinstance(value.get("caption_presets", {}), dict):
        raise LLMContractError("caption preset settings are invalid")
    # Preserve unrelated existing settings, including legacy extension fields.
    # Only the Caption authority is canonicalized, never write both defaults.
    value.setdefault("schema_version", 1)
    value["revision"] = value.get("revision", 0) + 1
    value.setdefault("default_presets", {})[CAPTION_TYPE] = default_id or ""
    value.pop("default_caption_preset_id", None)
    value.pop("caption_legacy_imported", None)
    state = value.setdefault("caption_presets", {"schema_version": 1, "imports": {}})
    state.setdefault("schema_version", 1)
    state.setdefault("imports", {})
    if imports is not None:
        state["imports"] = imports
    changes = _preset_changes(validated, migrating=migrating)
    target = settings_path()
    if target.is_file():
        changes[target.with_suffix(".json.bak")] = _bytes(target)
    changes[target] = _json_bytes(value)
    return changes


def save_presets(items, *, expected_revision=None):
    validated = _validate_items(items)
    with _store_guard():
        if expected_revision is not None and expected_revision != document_revision():
            raise LLMContractError("caption preset revision conflict")
        _transaction(_save(validated, settings()["default_caption_preset_id"]))
        return validated


def save_settings(default_caption_preset_id):
    with _store_guard():
        _transaction(_save(list_presets(), default_caption_preset_id))
        return settings()


def save_document(payload, *, mark_legacy_imported=False):
    with _store_guard():
        if not isinstance(payload, dict) or set(payload) - {"presets", "settings", "revision"}:
            raise LLMContractError("caption preset document is invalid")
        if payload.get("revision") != document_revision():
            raise LLMContractError("caption preset revision conflict")
        validated = _validate_items(payload.get("presets"))
        options = payload.get("settings", {})
        if not isinstance(options, dict) or set(options) - {"default_caption_preset_id", "legacy_imported"}:
            raise LLMContractError("caption preset settings are invalid")
        if "legacy_imported" in options and options["legacy_imported"] is not settings()["legacy_imported"]:
            raise LLMContractError("legacy import state is read-only")
        if mark_legacy_imported:
            raise LLMContractError("legacy import requires preview and confirmation")
        _transaction(_save(validated, options.get("default_caption_preset_id")))
        return document()


def _import_source(payload):
    source = payload.get("source")
    if source not in {"browser", "legacy_config", "user_data"}:
        raise LLMContractError("caption import source is invalid")
    if source == "user_data":
        if "presets" in payload:
            raise LLMContractError("user_data import source is server-owned")
        records = [(path, raw) for path, raw in _records() if is_caption(raw) and
                   (raw.get("kind") != "caption_prompt" or raw.get("train_type") != CAPTION_TYPE)]
        raw_items = [raw for _path, raw in records]
        source_value = [{"path": path.name, "raw": raw} for path, raw in records]
        if not records:
            # After a successful in-place migration the original files are no
            # longer legacy. Resolve the receipt's immutable source snapshot so
            # repeating the same import returns the same successful receipt.
            previous = [receipt for receipt in _settings_raw().get("caption_presets", {}).get("imports", {}).values()
                        if receipt.get("source") == "user_data"]
            if previous:
                snapshot = user_data_root() / previous[-1]["snapshot"]
                preserved = _read_json(snapshot, {})
                source_value = preserved.get("presets", [])
                raw_items = [item["raw"] for item in source_value]
    else:
        raw_items = payload.get("presets")
        if not isinstance(raw_items, list) or len(raw_items) > 24:
            raise LLMContractError("caption import presets must be an array of at most 24 objects")
        records, source_value = [], raw_items
    # A migration snapshot is deliberately only a bounded preset source, never
    # the parent config document (which could contain an API key).
    from mikazuki.user_data import without_credentials
    if without_credentials(source_value) != source_value:
        raise LLMContractError("caption import cannot contain credentials")
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise LLMContractError("caption import preset is invalid")
        if raw.get("train_type") == CAPTION_TYPE and "config" in raw:
            items.append(from_envelope(raw))
        else:
            items.append(validate_preset({**raw, "kind": "caption_prompt"}))
    fingerprint = _hash({"source": source, "presets": source_value})
    return source, fingerprint, items, records, source_value


def preview_import(payload):
    with _store_guard():
        if not isinstance(payload, dict) or set(payload) - {"source", "presets", "id_map", "default_preset_id", "confirmed", "preview_revision", "revision"}:
            raise LLMContractError("caption import request is invalid")
        source, fingerprint, items, records, source_value = _import_source(payload)
        id_map = payload.get("id_map", {})
        if not isinstance(id_map, dict) or set(id_map) - {item["id"] for item in items}:
            raise LLMContractError("caption import id_map is invalid")
        current = list_presets()
        record_ids = {raw.get("id", path.stem).casefold() for path, raw in records}
        retained = [item for item in current if item["id"].casefold() not in record_ids]
        occupied = {path.stem.casefold() for path, _raw in _records() if path.stem.casefold() not in record_ids}
        proposed, conflicts, mapped = [], [], {}
        for item in items:
            identifier = id_map.get(item["id"], item["id"])
            candidate = validate_preset({**item, "id": identifier})
            mapped[item["id"]] = identifier
            if identifier.casefold() in occupied:
                conflicts.append({"id": item["id"], "target_id": identifier, "reason": "id_collision"})
            occupied.add(identifier.casefold())
            proposed.append(candidate)
        default_id = payload.get("default_preset_id", settings()["default_caption_preset_id"])
        default_id = mapped.get(default_id, default_id)
        if default_id is not None and default_id not in {item["id"] for item in retained + proposed}:
            conflicts.append({"id": default_id, "reason": "missing_default"})
        state = _settings_raw().get("caption_presets", {})
        receipt = state.get("imports", {}).get(fingerprint)
        result = {"source": source, "source_fingerprint": fingerprint, "revision": document_revision(),
                  "presets": proposed, "id_map": mapped, "conflicts": conflicts,
                  "default_preset_id": default_id, "already_imported": receipt is not None, "receipt": receipt}
        result["preview_revision"] = _hash(result)[:24]
        return result


def commit_import(payload):
    with _store_guard():
        if not isinstance(payload, dict) or payload.get("confirmed") is not True:
            raise LLMContractError("caption import confirmation is required")
        preview = preview_import(payload)
        if preview["already_imported"]:
            return {"document": document(), "receipt": preview["receipt"]}
        if payload.get("revision") != preview["revision"] or payload.get("preview_revision") != preview["preview_revision"]:
            raise LLMContractError("caption import revision conflict; preview again")
        if preview["conflicts"]:
            raise LLMContractError("caption import has unresolved id/default conflicts")
        source, fingerprint, _items, records, source_value = _import_source(payload)
        replaced = {raw.get("id", path.stem).casefold() for path, raw in records}
        current = [item for item in list_presets() if item["id"].casefold() not in replaced]
        validated = _validate_items(current + preview["presets"])
        snapshot = user_data_root() / "migrations" / "caption-presets" / f"{fingerprint}.source.json"
        snapshot_bytes = _json_bytes({"source": source, "presets": source_value})
        existing = _bytes(snapshot)
        if existing is not None and existing != snapshot_bytes:
            raise LLMContractError("caption import source snapshot conflict")
        receipt = {"source": source, "source_fingerprint": fingerprint, "ids": preview["id_map"],
                   "snapshot": snapshot.relative_to(user_data_root()).as_posix()}
        state = _settings_raw().get("caption_presets", {})
        imports = {**state.get("imports", {}), fingerprint: receipt}
        changes = _save(validated, preview["default_preset_id"], imports=imports, migrating=True)
        if existing is None:
            changes[snapshot] = snapshot_bytes
        _transaction(changes)
        return {"document": document(), "receipt": receipt}


def import_legacy(items, *, expected_revision):
    """Compatibility entry, never silently choose a winner for colliding IDs."""
    payload = {"source": "legacy_config", "presets": items}
    preview = preview_import(payload)
    return commit_import({**payload, "confirmed": True, "revision": expected_revision,
                          "preview_revision": preview["preview_revision"]})["document"]

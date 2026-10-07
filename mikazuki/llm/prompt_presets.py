from __future__ import annotations

import copy
import base64
import hashlib
import json
import os
import re
import threading
import tempfile
import time
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .config import LLMContractError

_LANGUAGES = {"zh-CN", "zh-TW", "en", "ja"}
_KINDS = {"caption_prompt"}
_LOCK = threading.RLock()
_LOCK_OWNER = threading.local()
_JOURNAL = ".caption-preset-transaction.json"


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
    _check_path(path)
    if not path.is_file():
        return copy.deepcopy(default)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LLMContractError(f"user data is unreadable: {path.name}") from exc
    return value


def list_presets() -> list[dict[str, Any]]:
    with _store_guard():
        directory = presets_dir()
        _check_path(directory)
        if not directory.is_dir():
            return []
        result = []
        for path in sorted(directory.glob("*.json")):
            raw = _read_json(path, {})
            if isinstance(raw, dict) and raw.get("kind") == "caption_prompt":
                result.append(validate_preset(raw))
        return result


def document_revision() -> str:
    with _store_guard():
        # Include all settings fields, so another settings editor cannot silently
        # overwrite changes through this Caption-only projection.
        value = {"presets": list_presets(), "settings": _read_json(settings_path(), {})}
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def _check_path(path: Path) -> None:
    root = user_data_root().absolute()
    try:
        path.absolute().relative_to(root)
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise LLMContractError("caption preset path escapes user_data") from None
    current = path.absolute()
    while True:
        if current.exists() or current.is_symlink():
            attributes = getattr(current.lstat(), "st_file_attributes", 0)
            if current.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise LLMContractError("user data cannot use symbolic links or junctions")
        if current == root:
            break
        current = current.parent


def _bytes(path: Path) -> bytes | None:
    _check_path(path)
    return path.read_bytes() if path.exists() else None


def _encoded(value: bytes | None) -> str | None:
    return None if value is None else base64.b64encode(value).decode("ascii")


def _decoded(value) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LLMContractError("caption preset transaction is invalid")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError:
        raise LLMContractError("caption preset transaction is invalid") from None


def _json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_bytes(target: Path, value: bytes | None) -> None:
    _check_path(target)
    if value is None:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".caption-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        _check_path(target)
        os.replace(temporary_name, target)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _recover() -> None:
    journal_path = user_data_root() / _JOURNAL
    journal = _read_json(journal_path, None)
    if journal is None:
        return
    if not isinstance(journal, dict) or journal.get("schema_version") != 1 or journal.get("state") not in {"prepared", "committed"} or not isinstance(journal.get("files"), list):
        raise LLMContractError("caption preset transaction is invalid")
    files = []
    seen = set()
    for entry in journal["files"]:
        if not isinstance(entry, dict):
            raise LLMContractError("caption preset transaction is invalid")
        relative = entry.get("path")
        if not isinstance(relative, str) or not (relative in {"settings.json", "settings.json.bak"} or re.fullmatch(r"presets/[A-Za-z0-9][A-Za-z0-9._-]*\.json(?:\.bak)?", relative)) or relative.casefold() in seen:
            raise LLMContractError("caption preset transaction path is invalid")
        seen.add(relative.casefold())
        target = user_data_root() / relative
        _check_path(target)
        before, after = _decoded(entry.get("before")), _decoded(entry.get("after"))
        files.append((target, before, after))
    if journal["state"] == "prepared":
        # Do not erase an unrelated edit made outside the cooperating lock.
        if any(_bytes(target) not in (before, after) for target, before, after in files):
            raise LLMContractError("caption preset recovery conflict")
        for target, before, _after in reversed(files):
            if _bytes(target) != before:
                _atomic_bytes(target, before)
    journal_path.unlink()


@contextmanager
def _store_guard():
    with _LOCK:
        root = user_data_root()
        if getattr(_LOCK_OWNER, "root", None) == str(root.absolute()):
            yield
            return
        _check_path(root)
        root.mkdir(parents=True, exist_ok=True)
        lock_path = root / ".caption-presets.lock"
        _check_path(lock_path)
        with lock_path.open("a+b") as stream:
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"0")
                stream.flush()
            deadline = time.monotonic() + 5.0
            while True:
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise LLMContractError("caption preset store is busy") from None
                    time.sleep(.025)
            _LOCK_OWNER.root = str(root.absolute())
            try:
                _recover()
                yield
            finally:
                _LOCK_OWNER.root = None
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _transaction(changes: dict[Path, bytes | None]) -> None:
    files = [{"path": target.relative_to(user_data_root()).as_posix(), "before": _encoded(_bytes(target)), "after": _encoded(value)} for target, value in changes.items()]
    if all(entry["before"] == entry["after"] for entry in files):
        return
    journal_path = user_data_root() / _JOURNAL
    journal = {"schema_version": 1, "state": "prepared", "files": files}
    _atomic_bytes(journal_path, _json_bytes(journal))
    try:
        for target, value in changes.items():
            _atomic_bytes(target, value)
        journal["state"] = "committed"
        _atomic_bytes(journal_path, _json_bytes(journal))
    except BaseException:
        _recover()
        raise
    journal_path.unlink()


def _validate_items(items) -> list[dict]:
    if not isinstance(items, list) or len(items) > 24:
        raise LLMContractError("caption presets must be an array of at most 24 objects")
    validated = [validate_preset(item) for item in items]
    if len({item["id"].casefold() for item in validated}) != len(validated):
        raise LLMContractError("caption preset ids must be unique")
    return validated


def _preset_changes(validated: list[dict]) -> dict[Path, bytes | None]:
    directory = presets_dir()
    _check_path(directory)
    wanted = {item["id"].casefold(): item for item in validated}
    changes = {}
    for path in sorted(directory.glob("*.json")):
        raw = _read_json(path, {})
        existing_id = path.stem.casefold()
        if existing_id in wanted and (not isinstance(raw, dict) or raw.get("kind") != "caption_prompt" or path.stem != wanted[existing_id]["id"]):
            raise LLMContractError("caption preset id collides with another preset type or spelling")
        if isinstance(raw, dict) and raw.get("kind") == "caption_prompt":
            validate_preset(raw)
            changes[path.with_suffix(".json.bak")] = _bytes(path)
            if existing_id not in wanted:
                changes[path] = None
    for item in validated:
        changes[directory / f"{item['id']}.json"] = _json_bytes(item)
    return changes


def save_presets(items: list[dict[str, Any]], *, expected_revision: str | None = None) -> list[dict[str, Any]]:
    validated = _validate_items(items)
    with _store_guard():
        if expected_revision is not None and expected_revision != document_revision():
            raise LLMContractError("caption preset revision conflict")
        _transaction(_preset_changes(validated))
        return validated


def settings() -> dict[str, Any]:
    with _store_guard():
        value = _read_json(settings_path(), {})
        if not isinstance(value, dict):
            raise LLMContractError("user settings must be an object")
        return {"default_caption_preset_id": value.get("default_caption_preset_id") or None, "legacy_imported": value.get("caption_legacy_imported") is True}


def document() -> dict:
    with _store_guard():
        return {"presets": list_presets(), "settings": settings(), "revision": document_revision()}


def save_settings(default_caption_preset_id: str | None) -> dict[str, Any]:
    with _store_guard():
        if default_caption_preset_id is not None:
            default_caption_preset_id = _text(default_caption_preset_id, "default_caption_preset_id", 80)
            if default_caption_preset_id not in {item["id"] for item in list_presets()}:
                raise LLMContractError("default caption preset does not exist")
        target = settings_path()
        value = _read_json(target, {})
        if not isinstance(value, dict):
            raise LLMContractError("user settings must be an object")
        value.setdefault("schema_version", 1)
        value["default_caption_preset_id"] = default_caption_preset_id
        changes = {target: _json_bytes(value)}
        if target.is_file():
            changes[target.with_suffix(".json.bak")] = _bytes(target)
        _transaction(changes)
        return settings()


def save_document(payload: dict, *, mark_legacy_imported: bool = False) -> dict:
    with _store_guard():
        if not isinstance(payload, dict) or set(payload) - {"presets", "settings", "revision"}:
            raise LLMContractError("caption preset document is invalid")
        if payload.get("revision") != document_revision():
            raise LLMContractError("caption preset revision conflict")
        validated = _validate_items(payload.get("presets"))
        options = payload.get("settings", {})
        if not isinstance(options, dict) or set(options) - {"default_caption_preset_id", "legacy_imported"}:
            raise LLMContractError("caption preset settings are invalid")
        default_id = options.get("default_caption_preset_id")
        if default_id is not None and default_id not in {item["id"] for item in validated}:
            raise LLMContractError("default caption preset does not exist")
        # Settings validation must precede any preset mutation.
        existing_settings = _read_json(settings_path(), {})
        if not isinstance(existing_settings, dict):
            raise LLMContractError("user settings must be an object")
        if "legacy_imported" in options and options["legacy_imported"] is not (existing_settings.get("caption_legacy_imported") is True):
            raise LLMContractError("legacy import state is read-only")
        changes = _preset_changes(validated)
        existing_settings.setdefault("schema_version", 1)
        existing_settings["default_caption_preset_id"] = default_id
        if mark_legacy_imported:
            existing_settings["caption_legacy_imported"] = True
        target = settings_path()
        if target.is_file():
            changes[target.with_suffix(".json.bak")] = _bytes(target)
        changes[target] = _json_bytes(existing_settings)
        _transaction(changes)
        return document()


def import_legacy(items: list[dict], *, expected_revision: str) -> dict:
    """Explicit import only; existing user ids win and originals stay intact."""
    with _store_guard():
        if expected_revision != document_revision():
            raise LLMContractError("caption preset revision conflict")
        if settings()["legacy_imported"]:
            return document()
        current = {item["id"].casefold(): item for item in list_presets()}
        for item in items:
            migrated = validate_preset({**{key: value for key, value in item.items() if key != "revision"}, "kind": "caption_prompt"})
            current.setdefault(migrated["id"].casefold(), migrated)
        return save_document({"presets": list(current.values()), "settings": settings(), "revision": expected_revision}, mark_legacy_imported=True)

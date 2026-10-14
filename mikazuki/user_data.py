"""Durable user configuration. No browser or engine imports at startup."""

import copy
import json
import os
import re
import tempfile
import threading
import time
import datetime
from contextlib import contextmanager
from pathlib import Path
from mikazuki import user_data_transactions as tx


MAX_BYTES = 1024 * 1024
ENGINES = {"kohya", "anima-fast", "musubi", "ai-toolkit", "diffsynth"}
_LOCK = threading.RLock()


class UserDataError(ValueError):
    pass


class RevisionConflict(UserDataError):
    pass


def without_credentials(value):
    """Remove credential fields recursively, without matching tokenizer parameters."""
    if isinstance(value, dict):
        def sensitive(key):
            key = re.sub(r"(?<!^)(?=[A-Z])", "_", str(key)).lower().replace("-", "_")
            return key in {"auth", "authorization", "credentials", "api_key", "apikey", "token", "secret", "password"} or key.endswith(
                ("_api_key", "_token", "_secret", "_password"))
        return {key: without_credentials(item) for key, item in value.items() if not sensitive(key)}
    if isinstance(value, list):
        return [without_credentials(item) for item in value]
    return value


def _configuration_snapshot(path):
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8-sig")
        suffix = source.suffix.lower()
        if suffix == ".toml":
            import toml
            value = without_credentials(toml.loads(text))
            serialized = toml.dumps(value)
        elif suffix in {".yaml", ".yml"}:
            import yaml
            value = without_credentials(yaml.safe_load(text))
            serialized = yaml.safe_dump(value, allow_unicode=True)
        elif suffix == ".json":
            value = without_credentials(json.loads(text))
            serialized = json.dumps(value, ensure_ascii=False, allow_nan=False)
        else:
            raise UserDataError("Unsupported configuration format")
        _object(value, "configuration")
        return suffix, value, serialized
    except Exception as exc:
        raise UserDataError("Task configuration snapshot is missing or invalid") from exc


def _object(value, label):
    if not isinstance(value, dict):
        raise UserDataError(f"{label} must be an object")


def _keys(value, allowed, label):
    _object(value, label)
    if set(value) - set(allowed):
        raise UserDataError(f"Unsupported field in {label}")


def _string(value, label, allow_empty=False):
    if not isinstance(value, str) or len(value) > 8192 or "\0" in value:
        raise UserDataError(f"{label} must be a bounded string")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise UserDataError(f"{label} must contain valid Unicode")
    if not allow_empty and not value.strip():
        raise UserDataError(f"{label} must not be empty")


def _boolean(value, label):
    if type(value) is not bool:
        raise UserDataError(f"{label} must be boolean")


def _mapping(value, label):
    _object(value, label)
    if len(value) > 1000:
        raise UserDataError(f"{label} has too many entries")
    for key, item in value.items():
        _string(key, label)
        _string(item, label, allow_empty=True)


def validate_settings(value):
    _keys(value, {"schema_version", "revision", "startup", "engine_prefs", "engine_order",
                  "paths", "default_presets", "tasks", "caption_presets",
                  "default_caption_preset_id", "caption_legacy_imported"}, "settings")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise UserDataError("Unsupported settings schema_version")
    if type(value.get("revision")) is not int or value["revision"] < 0:
        raise UserDataError("Invalid settings revision")
    if "default_caption_preset_id" in value and value["default_caption_preset_id"] is not None:
        _string(value["default_caption_preset_id"], "default caption preset")
    if "caption_legacy_imported" in value:
        _boolean(value["caption_legacy_imported"], "caption legacy imported")
    if "caption_presets" in value:
        state = value["caption_presets"]
        _keys(state, {"schema_version", "imports"}, "caption_presets")
        if type(state.get("schema_version")) is not int or state.get("schema_version") != 1:
            raise UserDataError("Invalid caption_presets schema")
        _object(state.get("imports"), "caption import receipts")
        for fingerprint, receipt in state["imports"].items():
            if not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
                raise UserDataError("Invalid caption import fingerprint")
            _keys(receipt, {"source", "source_fingerprint", "ids", "snapshot"}, "caption import receipt")
            if receipt.get("source_fingerprint") != fingerprint or receipt.get("source") not in {"browser", "legacy_config", "user_data"}:
                raise UserDataError("Invalid caption import receipt")
            _mapping(receipt.get("ids"), "caption import ids")
            if receipt.get("snapshot") != f"migrations/caption-presets/{fingerprint}.source.json":
                raise UserDataError("Invalid caption import snapshot")
    if "tasks" in value:
        tasks = value["tasks"]
        _keys(tasks, {"auto_retry_max"}, "tasks")
        if "auto_retry_max" in tasks and (type(tasks["auto_retry_max"]) is not int
                                          or not 0 <= tasks["auto_retry_max"] <= 9):
            raise UserDataError("tasks.auto_retry_max must be an integer between 0 and 9")
    if "engine_prefs" in value:
        prefs = value["engine_prefs"]
        _keys(prefs, {"defaultEngine", "rememberLast", "lastByModel"}, "engine_prefs")
        if "defaultEngine" in prefs and (
            not isinstance(prefs["defaultEngine"], str) or prefs["defaultEngine"] not in ENGINES
        ):
            raise UserDataError("Unknown default engine")
        if "rememberLast" in prefs:
            _boolean(prefs["rememberLast"], "rememberLast")
        if "lastByModel" in prefs:
            _object(prefs["lastByModel"], "lastByModel")
            for model, selection in prefs["lastByModel"].items():
                _string(model, "model")
                _keys(selection, {"engine", "target"}, "selection")
                if not isinstance(selection.get("engine"), str) or selection["engine"] not in ENGINES:
                    raise UserDataError("Unknown remembered engine")
                _string(selection.get("target"), "target")
    if "engine_order" in value:
        order = value["engine_order"]
        if not isinstance(order, list) or any(not isinstance(x, str) or x not in ENGINES for x in order):
            raise UserDataError("Invalid engine order")
        if len(set(order)) != len(order):
            raise UserDataError("Duplicate engine order entry")
    if "paths" in value:
        paths = value["paths"]
        _keys(paths, {"models", "tagger_models", "python", "datasets", "outputs"}, "paths")
        for key, item in paths.items():
            if key in {"models", "tagger_models", "python"}:
                _mapping(item, key)
            else:
                _string(item, key, allow_empty=True)
    if "default_presets" in value:
        _mapping(value["default_presets"], "default_presets")
    if "startup" in value:
        _keys(value["startup"], {"gui", "monitor", "tensorboard"}, "startup")
        for service, config in value["startup"].items():
            allowed = {"port", "port_conflict"}
            allowed |= {"host", "open_browser"} if service == "gui" else {"enabled"}
            allowed |= {"mode"} if service == "monitor" else {"host"}
            _keys(config, allowed, service)
            if "port" in config and (type(config["port"]) is not int or not 1 <= config["port"] <= 65535):
                raise UserDataError(f"Invalid {service} port")
            if "host" in config:
                _string(config["host"], f"{service} host")
            for flag in ("enabled", "open_browser"):
                if flag in config:
                    _boolean(config[flag], flag)
            if "mode" in config and config["mode"] != "integrated":
                raise UserDataError("Only integrated monitoring is supported")
            policies = {"error", "next_available"} if service == "gui" else {"error", "next_available", "disable"}
            if "port_conflict" in config and (
                not isinstance(config["port_conflict"], str) or config["port_conflict"] not in policies
            ):
                raise UserDataError(f"Invalid {service} conflict policy")


def _merge(target, patch):
    result = copy.deepcopy(target)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class UserDataStore:
    def __init__(self, root=None):
        self.root = tx.resolve_root(root)

    def _path(self, name):
        path = self.root / name
        try:
            tx.check_path(path, self.root)
        except tx.TransactionError as exc:
            raise UserDataError(str(exc)) from exc
        if path.is_symlink() or path.resolve().parent != self.root.resolve():
            raise UserDataError("User data file must remain within its directory")
        return path

    def _read(self, name):
        path = self._path(name)
        if not path.exists():
            return {"schema_version": 1, "revision": 0}
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise UserDataError("User data file is too large")
            value = json.loads(raw.decode("utf-8-sig"))
            _object(value, name)
            value.setdefault("schema_version", 1)
            value.setdefault("revision", 0)
            return value
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise UserDataError(f"Cannot read {name}; original file has been preserved") from exc

    @contextmanager
    def _locked(self, create=True):
        try:
            with tx.guard(self.root, create=create):
                yield
        except tx.TransactionError as exc:
            raise UserDataError(str(exc)) from exc

    def _caption(self, operation, *args, **kwargs):
        from mikazuki.llm.config import LLMContractError
        try:
            with tx.at_root(self.root):
                return operation(*args, **kwargs)
        except (LLMContractError, tx.TransactionError) as exc:
            error = RevisionConflict if "revision conflict" in str(exc).lower() else UserDataError
            raise error(str(exc)) from exc

    def _stage(self, name, raw):
        fd, temporary = tempfile.mkstemp(prefix=f".{name}-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            return temporary
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def _write(self, name, value, backup=True):
        raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
        if len(raw) > MAX_BYTES:
            raise UserDataError("User data file is too large")
        path = self._path(name)
        temporary = None
        previous_temporary = None
        previous = self._read(name) if backup and path.exists() else None
        backup_path = self._path(name + ".bak") if previous is not None else None
        try:
            if previous is not None:
                previous_raw = json.dumps(
                    previous, ensure_ascii=False, indent=2, allow_nan=False
                ).encode("utf-8")
                # Keep the old primary durable without touching the old backup.
                previous_temporary = self._stage(name + "-previous", previous_raw)
            temporary = self._stage(name, raw)
            os.replace(temporary, path)
            temporary = None
            if previous_temporary is not None:
                try:
                    os.replace(previous_temporary, backup_path)
                    previous_temporary = None
                except OSError:
                    # Reuse the durable copy: rollback must not allocate or write.
                    try:
                        os.replace(previous_temporary, path)
                        previous_temporary = None
                    except OSError as exc:
                        recovery_name = Path(previous_temporary).name
                        previous_temporary = None
                        raise UserDataError(
                            "Backup and rollback failed; previous settings preserved in "
                            f"{recovery_name}; reload settings before retrying"
                        ) from exc
                    raise
        except OSError as exc:
            raise UserDataError(f"Cannot save {name}; no successful save was recorded") from exc
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
            if previous_temporary is not None:
                Path(previous_temporary).unlink(missing_ok=True)

    def read_settings(self):
        with self._locked(create=False):
            value = self._read("settings.json")
            validate_settings(value)
            return value

    def model_path(self, category, model_id):
        if category not in {"tagger_models", "models", "python"}:
            raise UserDataError("Unknown model path category")
        value = self.read_settings().get("paths", {}).get(category, {}).get(model_id)
        if not value:
            return None
        path = Path(value).expanduser()
        return (self.root.parent / path).resolve() if not path.is_absolute() else path.resolve()

    def patch_settings(self, patch, revision):
        _object(patch, "patch")
        if {"revision", "schema_version", "caption_presets", "default_caption_preset_id", "caption_legacy_imported"} & set(patch):
            raise UserDataError("Revision, schema and caption migration state are managed by the server")
        with self._locked():
            current = self.read_settings()
            if type(revision) is not int or revision != current["revision"]:
                raise RevisionConflict("Settings changed; reload before saving")
            updated = _merge(current, patch)
            updated["revision"] += 1
            validate_settings(updated)
            default_id = updated.get("default_presets", {}).get("tagger-caption")
            if default_id:
                from mikazuki.llm import prompt_presets
                known = {item["id"] for item in self._caption(prompt_presets.list_presets)}
                if default_id not in known:
                    raise UserDataError("Default caption preset does not exist")
            self._write("settings.json", updated)
            return updated

    def _credentials(self):
        data = self._read("auth.json")
        _keys(data, {"schema_version", "revision", "providers"}, "auth")
        if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
            raise UserDataError("Invalid auth schema or revision")
        if type(data.get("revision")) is not int or data["revision"] < 0:
            raise UserDataError("Invalid auth schema or revision")
        _mapping(data.get("providers", {}), "providers")
        return data

    def credential_metadata(self):
        data = self._credentials()
        return {"schema_version": 1, "revision": data["revision"],
                "providers": {name: {"configured": bool(secret)}
                              for name, secret in data.get("providers", {}).items()}}

    def get_credential(self, provider):
        """Backend-only accessor. Never return this value from an API."""
        return self._credentials().get("providers", {}).get(provider)

    def set_credential(self, provider, secret, revision):
        if not isinstance(provider, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", provider):
            raise UserDataError("Invalid credential provider")
        if secret is not None:
            _string(secret, "credential")
        with self._locked():
            data = self._credentials()
            if type(revision) is not int or revision != data["revision"]:
                raise RevisionConflict("Credentials changed; reload before saving")
            providers = data.setdefault("providers", {})
            if secret is None:
                providers.pop(provider, None)
            else:
                providers[provider] = secret
            _mapping(providers, "providers")
            data["revision"] += 1
            # Do not leave deleted/replaced secrets in an automatic backup.
            self._write("auth.json", data, backup=False)
            return self.credential_metadata()

    def _safe_id(self, value, label="id"):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
            raise UserDataError(f"Invalid {label}")
        return value

    def _record_path(self, category, record_id):
        self._safe_id(record_id)
        directory = self.root / category
        try:
            tx.check_path(directory, self.root)
        except tx.TransactionError as exc:
            raise UserDataError(str(exc)) from exc
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{record_id}.json"
        if path.resolve().parent != directory.resolve() or path.is_symlink():
            raise UserDataError("User data record must remain within its directory")
        return path

    def list_presets(self, train_type=None):
        from mikazuki.llm import prompt_presets as caption
        with self._locked(create=False):
            if train_type == caption.CAPTION_TYPE:
                return [caption.to_envelope(item) for item in self._caption(caption.list_presets)]
            directory = self.root / "presets"
            tx.check_path(directory, self.root)
            if not directory.is_dir():
                return []
            result = []
            for path in sorted(directory.glob("*.json")):
                try:
                    tx.check_path(path, self.root)
                    item = json.loads(path.read_text(encoding="utf-8"))
                    if caption.is_caption(item) or (train_type and item.get("train_type") != train_type):
                        continue
                    result.append(item)
                except (OSError, UnicodeError, json.JSONDecodeError):
                    continue
            return result

    def preset_document(self, train_type=None):
        with self._locked(create=False):
            result = {"presets": self.list_presets(train_type)}
            if train_type == "tagger-caption":
                from mikazuki.llm import prompt_presets
                result["revision"] = self._caption(prompt_presets.document_revision)
            return result

    def _raw_preset(self, preset_id):
        self._safe_id(preset_id)
        path = self.root / "presets" / f"{preset_id}.json"
        tx.check_path(path, self.root)
        if not path.is_file():
            raise UserDataError("Preset not found")
        try:
            item = tx.read_json(path, {})
            _object(item, "preset")
            return item
        except tx.TransactionError as exc:
            raise UserDataError(str(exc)) from exc

    def get_preset(self, preset_id):
        from mikazuki.llm import prompt_presets as caption
        with self._locked(create=False):
            item = self._raw_preset(preset_id)
            if caption.is_caption(item):
                result = self._caption(caption.from_envelope, item)
                result = caption.to_envelope(result)
                result["document_revision"] = self._caption(caption.document_revision)
                return result
            return item

    def save_preset(self, preset_id, value, replace=False):
        from mikazuki.llm import prompt_presets as caption
        self._safe_id(preset_id, "preset id")
        _object(value, "preset")
        _keys(value, {"id", "name", "description", "train_type", "config", "created_at", "updated_at", "document_revision"}, "preset")
        _string(value.get("name"), "preset name")
        _object(value.get("config"), "preset config")
        if without_credentials(value["config"]) != value["config"]:
            raise UserDataError("Preset cannot contain credentials")
        with self._locked():
            path = self.root / "presets" / f"{preset_id}.json"
            tx.check_path(path, self.root)
            existing = self._raw_preset(preset_id) if path.exists() else None
            if existing is not None and not replace:
                raise RevisionConflict("Preset already exists")
            is_caption = value.get("train_type") == caption.CAPTION_TYPE
            if existing is not None and caption.is_caption(existing) != is_caption:
                raise UserDataError("Preset domain identity is immutable")
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            value = copy.deepcopy(value)
            value["id"] = preset_id
            value.setdefault("created_at", now)
            value["updated_at"] = now
            revision = value.pop("document_revision", None)
            if is_caption:
                if not isinstance(revision, str) or not revision:
                    raise RevisionConflict("Caption document_revision is required; reload before saving")
                current = self._caption(caption.document)
                if revision != current["revision"]:
                    raise RevisionConflict("Caption preset revision conflict")
                item = self._caption(caption.from_envelope, value)
                items = [entry for entry in current["presets"] if entry["id"] != preset_id] + [item]
                saved = self._caption(caption.save_document, {**current, "presets": items})
                result = caption.to_envelope(next(entry for entry in saved["presets"] if entry["id"] == preset_id))
                result["document_revision"] = saved["revision"]
                return result
            if revision is not None:
                raise UserDataError("document_revision belongs to Caption presets")
            changes = {path: tx.json_bytes(value)}
            if path.exists():
                changes[path.with_suffix(".json.bak")] = tx.read_bytes(path)
            tx.transaction(changes)
            return value

    def patch_preset(self, preset_id, patch):
        with self._locked():
            current = self.get_preset(preset_id)
            # The caller must supply CAS for this write, not inherit the version
            # read by this operation and accidentally bypass client protection.
            current.pop("document_revision", None)
            if current.get("train_type") == "tagger-caption" and isinstance(patch.get("config"), dict):
                patch = {**patch, "config": {**current["config"], **patch["config"]}}
            current.update(patch)
            return self.save_preset(preset_id, current, True)

    def delete_preset(self, preset_id, document_revision=None):
        from mikazuki.llm import prompt_presets as caption
        with self._locked():
            item = self._raw_preset(preset_id)
            if caption.is_caption(item):
                if not isinstance(document_revision, str) or not document_revision:
                    raise RevisionConflict("Caption If-Match document revision is required")
                current = self._caption(caption.document)
                if document_revision != current["revision"]:
                    raise RevisionConflict("Caption preset revision conflict")
                if current["settings"]["default_caption_preset_id"] == preset_id:
                    raise UserDataError("Preset is selected as a default")
                self._caption(caption.save_document, {**current, "presets": [entry for entry in current["presets"] if entry["id"] != preset_id]})
                return
            if preset_id in self.read_settings().get("default_presets", {}).values():
                raise UserDataError("Preset is selected as a default")
            path = self.root / "presets" / f"{preset_id}.json"
            tx.transaction({path.with_suffix(".json.bak"): tx.read_bytes(path), path: None})

    def preview_caption_import(self, payload):
        from mikazuki.llm import prompt_presets
        return self._caption(prompt_presets.preview_import, payload)

    def commit_caption_import(self, payload):
        from mikazuki.llm import prompt_presets
        return self._caption(prompt_presets.commit_import, payload)

    def _write_path(self, path, value):
        raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
        if len(raw) > MAX_BYTES:
            raise UserDataError("User data file is too large")
        temporary = self._stage(path.name, raw)
        try:
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)

    def archive_task(self, task_id, metadata, config_path=None):
        metadata = {key: value for key, value in metadata.items() if key != "task_archive"}
        self._safe_id(task_id, "task id")
        engine = self._safe_id(str(metadata.get("backend") or "standard"), "engine")
        source_path = config_path or metadata.get("config_path")
        if not source_path:
            raise UserDataError("Task configuration snapshot is missing")
        snapshots = {"config": _configuration_snapshot(source_path)}
        if metadata.get("engine_config_path"):
            snapshots["engine_config"] = _configuration_snapshot(metadata["engine_config_path"])
        stamp = datetime.datetime.now(datetime.timezone.utc)
        folder = self.root / "tasks" / engine / stamp.strftime("%Y-%m-%d") / f"{stamp.strftime('%H%M%S')}_{task_id}"
        folder.mkdir(parents=True, exist_ok=False)
        record = {
            "task_id": task_id,
            "engine": engine,
            "created_at": stamp.isoformat(),
            "metadata": without_credentials(copy.deepcopy(metadata)),
            "config_path": str(config_path or metadata.get("config_path") or ""),
        }
        try:
            for key, (suffix, config, text) in snapshots.items():
                native = folder / f"{key.replace('_', '-')}{suffix}"
                native.write_text(text, encoding="utf-8")
                record[key + "_file"] = native.name
                record[key] = config
            self._write_path(folder / "task.json", record)
        except BaseException:
            import shutil
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return record

    def list_task_archives(self, train_type=None):
        root = self.root / "tasks"
        records = []
        if not root.is_dir():
            return records
        for path in root.glob("*/*/*/task.json"):
            try:
                item = without_credentials(json.loads(path.read_text(encoding="utf-8")))
                if train_type and item.get("metadata", {}).get("train_type") != train_type:
                    continue
                item["id"] = item["task_id"]
                item["train_type"] = item.get("metadata", {}).get("train_type")
                item["name"] = str(item.get("config", {}).get("output_name") or item["task_id"])
                records.append(item)
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
        return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)

    def get_task_archive(self, archive_id):
        for item in self.list_task_archives():
            if item.get("task_id") == archive_id:
                return item
        raise UserDataError("Task archive not found")

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


MAX_BYTES = 1024 * 1024
ENGINES = {"kohya", "anima-fast", "musubi", "ai-toolkit", "diffsynth"}
_LOCK = threading.RLock()


class UserDataError(ValueError):
    pass


class RevisionConflict(UserDataError):
    pass


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
                  "paths", "default_presets"}, "settings")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise UserDataError("Unsupported settings schema_version")
    if type(value.get("revision")) is not int or value["revision"] < 0:
        raise UserDataError("Invalid settings revision")
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
        self.root = Path(root).absolute() if root is not None else Path(__file__).resolve().parents[1] / "user_data"

    def _path(self, name):
        path = self.root / name
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
    def _locked(self):
        # Serialize threads and processes, including separate GUI instances.
        with _LOCK:
            self.root.mkdir(parents=True, exist_ok=True)
            lock_path = self._path(".write.lock")
            with lock_path.open("a+b") as stream:
                if stream.tell() == 0:
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                            break
                        except OSError as exc:
                            if time.monotonic() >= deadline:
                                raise UserDataError("User data is busy; retry saving") from exc
                            time.sleep(0.05)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    stream.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

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
        if "revision" in patch or "schema_version" in patch:
            raise UserDataError("Revision and schema_version are managed by the server")
        with self._locked():
            current = self.read_settings()
            if type(revision) is not int or revision != current["revision"]:
                raise RevisionConflict("Settings changed; reload before saving")
            updated = _merge(current, patch)
            updated["revision"] += 1
            validate_settings(updated)
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
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{record_id}.json"
        if path.resolve().parent != directory.resolve() or path.is_symlink():
            raise UserDataError("User data record must remain within its directory")
        return path

    def list_presets(self, train_type=None):
        directory = self.root / "presets"
        if not directory.is_dir():
            return []
        result = []
        for path in sorted(directory.glob("*.json")):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                if train_type and item.get("train_type") != train_type:
                    continue
                result.append(item)
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
        return result

    def get_preset(self, preset_id):
        path = self._record_path("presets", preset_id)
        if not path.is_file():
            raise UserDataError("Preset not found")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise UserDataError("Preset is invalid") from exc

    def save_preset(self, preset_id, value, replace=False):
        self._safe_id(preset_id, "preset id")
        _object(value, "preset")
        _keys(value, {"id", "name", "description", "train_type", "config", "created_at", "updated_at"}, "preset")
        _string(value.get("name"), "preset name")
        _object(value.get("config"), "preset config")
        for secret_key in ("api_key", "token", "secret", "password"):
            if secret_key in json.dumps(value["config"]).lower():
                raise UserDataError("Preset cannot contain credentials")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        value = copy.deepcopy(value)
        value["id"] = preset_id
        value.setdefault("created_at", now)
        value["updated_at"] = now
        path = self._record_path("presets", preset_id)
        with self._locked():
            if path.exists() and not replace:
                raise RevisionConflict("Preset already exists")
            self._write_path(path, value)
        return value

    def delete_preset(self, preset_id):
        path = self._record_path("presets", preset_id)
        with self._locked():
            if not path.exists():
                raise UserDataError("Preset not found")
            settings = self.read_settings()
            defaults = settings.get("default_presets", {})
            if preset_id in defaults.values():
                raise UserDataError("Preset is selected as a default")
            path.unlink()

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
        self._safe_id(task_id, "task id")
        engine = self._safe_id(str(metadata.get("backend") or "standard"), "engine")
        stamp = datetime.datetime.now(datetime.timezone.utc)
        folder = self.root / "tasks" / engine / stamp.strftime("%Y-%m-%d") / f"{stamp.strftime('%H%M%S')}_{task_id}"
        folder.mkdir(parents=True, exist_ok=False)
        record = {
            "task_id": task_id,
            "engine": engine,
            "created_at": stamp.isoformat(),
            "metadata": copy.deepcopy(metadata),
            "config_path": str(config_path or metadata.get("config_path") or ""),
        }
        try:
            if config_path and Path(config_path).is_file():
                source = Path(config_path)
                native = folder / f"config{source.suffix or '.json'}"
                native.write_bytes(source.read_bytes())
                record["config_file"] = native.name
                try:
                    if source.suffix.lower() == ".toml":
                        import toml
                        record["config"] = toml.loads(source.read_text(encoding="utf-8-sig"))
                    else:
                        record["config"] = json.loads(source.read_text(encoding="utf-8-sig"))
                except Exception as exc:
                    raise UserDataError("Task configuration snapshot is invalid") from exc
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
                item = json.loads(path.read_text(encoding="utf-8"))
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

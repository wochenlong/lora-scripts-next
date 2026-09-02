from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path


class MarketplaceStore:
    """Small atomic registry for installed versions and activation state."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._read())

    def get_plugin(self, plugin_id: str) -> dict | None:
        with self._lock:
            value = self._read()["plugins"].get(plugin_id)
            return copy.deepcopy(value) if value is not None else None

    def set_plugin(self, plugin_id: str, value: dict) -> None:
        with self._lock:
            data = self._read()
            data["plugins"][plugin_id] = copy.deepcopy(value)
            self._write(data)

    def remove_plugin(self, plugin_id: str) -> None:
        with self._lock:
            data = self._read()
            data["plugins"].pop(plugin_id, None)
            self._write(data)

    def _read(self) -> dict:
        if not self.path.is_file():
            return {"schema_version": 1, "plugins": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid marketplace registry: {self.path}") from exc
        if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("plugins"), dict):
            raise ValueError(f"invalid marketplace registry: {self.path}")
        return value

    def _write(self, value: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)


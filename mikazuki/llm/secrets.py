"""Runtime-only credentials shared by legacy translation and unified LLMs.

Only masks are persisted. A new backend process must receive keys again; no
environment file, companion secret file or reversible encoding is used.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

MASK = "********"
_credentials: dict[str, dict[tuple[str, ...], str]] = {}
_lock = threading.RLock()


def _namespace(path) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def _transform(value, credentials, *, masked, location=(), referenced=None):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            address = (*location, key)
            if key == "api_key" and isinstance(item, str):
                if referenced is not None:
                    referenced.add(address)
                secret = credentials.get(address, "") if item == MASK else item
                if secret:
                    credentials[address] = secret
                else:
                    credentials.pop(address, None)
                result[key] = MASK if masked and (secret or item == MASK) else secret
            else:
                result[key] = _transform(item, credentials, masked=masked, location=address, referenced=referenced)
        return result
    if isinstance(value, list):
        return [_transform(item, credentials, masked=masked,
                           location=(*location, str(item.get("id", index)) if isinstance(item, dict) else str(index)), referenced=referenced)
                for index, item in enumerate(value)]
    return value


def write_configuration(path, document):
    path = Path(path)
    with _lock:
        credentials = dict(_credentials.get(_namespace(path), {}))
        referenced = set()
        masked = _transform(document, credentials, masked=True, referenced=referenced)
        # Keep only keys still referenced by this document (including clears).
        credentials = {address: secret for address, secret in credentials.items()
                       if address in referenced}
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="llm-config-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
                json.dump(masked, output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
            _credentials[_namespace(path)] = credentials
        except Exception:
            if os.path.exists(temporary):
                os.unlink(temporary)
            raise


def read_configuration(path):
    path = Path(path)
    with _lock:
        document = json.loads(path.read_text(encoding="utf-8"))
        credentials = dict(_credentials.get(_namespace(path), {}))
        hydrated = _transform(document, credentials, masked=False)
        masked = _transform(document, credentials, masked=True)
        if masked != document:
            # Migrate legacy plaintext immediately using the same atomic writer.
            write_configuration(path, hydrated)
        else:
            _credentials[_namespace(path)] = credentials
        return hydrated

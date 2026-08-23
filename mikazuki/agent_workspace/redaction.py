"""Deterministic redaction for Agent context, artifacts and audit output."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|password|passwd|secret|cookie|private[_-]?key)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._~+/-]{12,})")
_REDACTED = "[configured]"


def redact(value: Any, *, key: str | None = None, replacement: str = _REDACTED) -> Any:
    """Return a deep, JSON-like copy with credentials represented by presence only."""
    if key and _SECRET_KEY.search(key):
        return replacement
    if isinstance(value, Mapping):
        return {str(k): redact(v, key=str(k), replacement=replacement) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item, replacement=replacement) for item in value]
    if isinstance(value, tuple):
        return [redact(item, replacement=replacement) for item in value]
    if isinstance(value, str) and _SECRET_VALUE.search(value):
        return _SECRET_VALUE.sub(replacement, value)
    return deepcopy(value)


def redact_for_log(value: Any) -> Any:
    """Alias used by audit writers; never logs raw credential values."""
    return redact(value)


__all__ = ["redact", "redact_for_log"]

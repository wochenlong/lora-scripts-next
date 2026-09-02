from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .errors import AgentDomainError

_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_BAD_PART = re.compile(r"[\x00:]")
_DEFAULT_EXTENSIONS = frozenset({".toml", ".json", ".txt", ".md"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class WorkspaceManifest:
    session_id: str
    purpose: str
    workspace_class: str
    root: str
    readonly_root: str
    writable_root: str
    allowed_extensions: frozenset[str] = _DEFAULT_EXTENSIONS
    max_files: int = 10
    max_bytes: int = 1024 * 1024
    max_file_bytes: int = 1024 * 1024
    source_snapshot_hash: str | None = None
    source_revision: str | None = None
    owner: str = "agent"
    expires_at: str | None = None
    version: str = "v1"

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["allowed_extensions"] = sorted(self.allowed_extensions)
        return value


class AgentWorkspace:
    """A workspace-relative, host-owned file boundary.

    The constructor accepts either an existing workspace root or a parent data
    directory plus a session id.  Every operation resolves and checks the path
    again, including immediately before writes, to reduce TOCTOU risk.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        session_id: str | None = None,
        purpose: str = "training-config",
        workspace_class: str | None = None,
        allowed_extensions: Iterable[str] = _DEFAULT_EXTENSIONS,
        max_files: int = 10,
        max_bytes: int = 1024 * 1024,
        max_file_bytes: int = 1024 * 1024,
        source_revision: str | None = None,
        source_snapshot_hash: str | None = None,
        expiry_seconds: int = 3600,
    ) -> None:
        if not isinstance(root, (str, os.PathLike)):
            raise TypeError("workspace root is required")
        root_path = Path(root).expanduser()
        if session_id:
            if not self._valid_session(session_id):
                raise AgentDomainError("WORKSPACE_INVALID", "Invalid workspace session id.")
            root_path = root_path / "agent-workspaces" / session_id
        root_path = root_path.absolute()
        if not root_path.name:
            raise AgentDomainError("WORKSPACE_INVALID", "Workspace root is invalid.")
        self.root = root_path
        self.readonly_root = root_path / "readonly"
        self.writable_root = root_path / "writable"
        self.manifest_root = root_path / "manifests"
        self.manifest_path = root_path / "workspace.json"
        extension_set = frozenset(self._normalize_extension(e) for e in allowed_extensions)
        if not extension_set or any(not e.startswith(".") for e in extension_set):
            raise AgentDomainError("WORKSPACE_INVALID", "Allowed file extensions are invalid.")
        if max_files < 1 or max_bytes < 1 or max_file_bytes < 1 or max_file_bytes > max_bytes:
            raise AgentDomainError("WORKSPACE_LIMIT_INVALID", "Workspace limits are invalid.")
        self.manifest = WorkspaceManifest(
            session_id=session_id or root_path.name,
            purpose=purpose,
            workspace_class=workspace_class or purpose,
            root=str(root_path),
            readonly_root=str(self.readonly_root),
            writable_root=str(self.writable_root),
            allowed_extensions=extension_set,
            max_files=max_files,
            max_bytes=max_bytes,
            max_file_bytes=max_file_bytes,
            source_snapshot_hash=source_snapshot_hash,
            source_revision=source_revision,
            expires_at=(_utc_now() + timedelta(seconds=expiry_seconds)).isoformat(),
        )

    @staticmethod
    def _valid_session(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value)) and value.casefold() not in _RESERVED

    @staticmethod
    def _normalize_extension(value: str) -> str:
        if not isinstance(value, str):
            raise AgentDomainError("WORKSPACE_INVALID", "Allowed file extensions are invalid.")
        value = value.strip().lower()
        return value if value.startswith(".") else "." + value

    def create(self) -> WorkspaceManifest:
        for path in (self.root, self.readonly_root, self.writable_root, self.manifest_root):
            path.mkdir(parents=True, exist_ok=True)
        self._write_json_atomic(self.manifest_path, self.manifest.as_dict())
        return self.manifest

    def resolve(self, relative_path: str, *, writable: bool = True, must_exist: bool = False) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise AgentDomainError("WORKSPACE_PATH_INVALID", "Workspace-relative path is required.")
        if "\x00" in relative_path or "/" not in relative_path and "\\" not in relative_path:
            # Single file names are valid; this branch intentionally only rejects NUL below.
            pass
        path_text = relative_path.replace("\\", "/")
        path = Path(path_text)
        if path.is_absolute() or re.match(r"^[A-Za-z]:", path_text) or path_text.startswith("//"):
            raise AgentDomainError("WORKSPACE_PATH_ESCAPE", "Absolute or UNC paths are not allowed.")
        parts = path.parts
        if any(part in {"", ".", ".."} for part in parts) or any(_BAD_PART.search(part) for part in parts):
            raise AgentDomainError("WORKSPACE_PATH_ESCAPE", "Path traversal or alternate streams are not allowed.")
        if any(part.casefold().split(".", 1)[0] in _RESERVED for part in parts):
            raise AgentDomainError("WORKSPACE_PATH_INVALID", "Reserved device names are not allowed.")
        if len(parts) > 32:
            raise AgentDomainError("WORKSPACE_PATH_INVALID", "Workspace path is too deep.")
        base = self.writable_root if writable else self.readonly_root
        candidate = base.joinpath(*parts)
        try:
            resolved_base = base.resolve(strict=False)
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(resolved_base)
        except (OSError, ValueError):
            raise AgentDomainError("WORKSPACE_PATH_ESCAPE", "Path escapes the Agent workspace.") from None
        self._reject_reparse(candidate)
        if must_exist and not candidate.is_file():
            raise AgentDomainError("WORKSPACE_NOT_FOUND", "Workspace file was not found.", status_code=404)
        return candidate

    @staticmethod
    def _reject_reparse(path: Path) -> None:
        current = path
        while True:
            try:
                if current.is_symlink():
                    raise AgentDomainError("WORKSPACE_REPARSE_REJECTED", "Reparse points are not allowed.")
                st = current.stat()
                attrs = getattr(st, "st_file_attributes", 0)
                if attrs & 0x400:
                    raise AgentDomainError("WORKSPACE_REPARSE_REJECTED", "Reparse points are not allowed.")
            except FileNotFoundError:
                pass
            if current.parent == current:
                break
            current = current.parent

    def read_bytes(self, relative_path: str, *, writable: bool = True) -> bytes:
        path = self.resolve(relative_path, writable=writable, must_exist=True)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise AgentDomainError("WORKSPACE_READ_FAILED", "Workspace file could not be read.", details={"reason": str(exc)}) from None
        if len(data) > self.manifest.max_file_bytes:
            raise AgentDomainError("WORKSPACE_LIMIT_EXCEEDED", "Workspace file exceeds the size limit.")
        return data

    def read_text(self, relative_path: str, *, writable: bool = True) -> str:
        try:
            return self.read_bytes(relative_path, writable=writable).decode("utf-8")
        except UnicodeDecodeError:
            raise AgentDomainError("WORKSPACE_ENCODING_INVALID", "Workspace text must be UTF-8.") from None

    def write_bytes(self, relative_path: str, data: bytes, *, overwrite: bool = True) -> dict[str, Any]:
        if not isinstance(data, bytes):
            raise TypeError("workspace data must be bytes")
        path = self.resolve(relative_path)
        if path.suffix.lower() not in self.manifest.allowed_extensions:
            raise AgentDomainError("WORKSPACE_EXTENSION_FORBIDDEN", "File extension is not allowed.")
        if len(data) > self.manifest.max_file_bytes:
            raise AgentDomainError("WORKSPACE_LIMIT_EXCEEDED", "Workspace file exceeds the size limit.")
        existing = list(self.writable_root.rglob("*"))
        file_count = sum(1 for item in existing if item.is_file())
        total = sum(item.stat().st_size for item in existing if item.is_file())
        if not path.exists() and file_count >= self.manifest.max_files:
            raise AgentDomainError("WORKSPACE_LIMIT_EXCEEDED", "Workspace file count exceeds the limit.")
        old_size = path.stat().st_size if path.exists() else 0
        if total - old_size + len(data) > self.manifest.max_bytes:
            raise AgentDomainError("WORKSPACE_LIMIT_EXCEEDED", "Workspace byte limit exceeded.")
        if path.exists() and not overwrite:
            raise AgentDomainError("WORKSPACE_CONFLICT", "Workspace file already exists.", status_code=409)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._reject_reparse(path)
        self._write_bytes_atomic(path, data)
        return {"path": path.relative_to(self.writable_root).as_posix(), "contentHash": _hash_bytes(data), "bytes": len(data)}

    def write_text(self, relative_path: str, text: str, *, overwrite: bool = True) -> dict[str, Any]:
        if not isinstance(text, str):
            raise TypeError("workspace text must be str")
        return self.write_bytes(relative_path, text.encode("utf-8"), overwrite=overwrite)

    def file_hash(self, relative_path: str, *, writable: bool = True) -> str:
        return _hash_bytes(self.read_bytes(relative_path, writable=writable))

    def source_revision_for(self, relative_path: str, *, writable: bool = False) -> str:
        return self.file_hash(relative_path, writable=writable)

    @staticmethod
    def _write_bytes_atomic(path: Path, data: bytes) -> None:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path)
        except OSError as exc:
            try:
                os.unlink(name)
            except OSError:
                pass
            raise AgentDomainError("WORKSPACE_WRITE_FAILED", "Workspace file could not be written.", details={"reason": str(exc)}) from None

    @classmethod
    def _write_json_atomic(cls, path: Path, data: dict[str, Any]) -> None:
        cls._write_bytes_atomic(path, (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))


__all__ = ["AgentWorkspace", "WorkspaceManifest"]

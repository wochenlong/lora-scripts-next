from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any, Iterable, Mapping

from .audit import CAPTION_EXTENSIONS, _hash_bytes, _reject_reparse
from .errors import DatasetReviewError

ALLOWED_TEXT_EXTENSIONS = frozenset(CAPTION_EXTENSIONS)


def _stable_hash(value: Any) -> str:
    return _hash_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _root(path: str | Path, *, create: bool = False) -> Path:
    value = Path(path).expanduser()
    if not value.is_absolute():
        value = value.absolute()
    if create:
        value.mkdir(parents=True, exist_ok=True)
    try:
        resolved = value.resolve(strict=True)
    except OSError:
        raise DatasetReviewError("DATASET_ROOT_INVALID", "Review root could not be resolved.", status_code=404) from None
    if not resolved.is_dir():
        raise DatasetReviewError("DATASET_ROOT_INVALID", "Review root must be a directory.")
    _reject_reparse(resolved)
    return resolved


def _safe_relative(root: Path, relative: str, *, allowed_extensions: frozenset[str], must_exist: bool = False) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise DatasetReviewError("DATASET_PATH_INVALID", "A relative caption path is required.")
    normalized = relative.replace("\\", "/")
    candidate_rel = Path(normalized)
    if candidate_rel.is_absolute() or normalized.startswith("//") or ":" in normalized:
        raise DatasetReviewError("DATASET_PATH_ESCAPE", "Absolute, UNC, or alternate-stream paths are not allowed.")
    if any(part in {"", ".", ".."} for part in candidate_rel.parts):
        raise DatasetReviewError("DATASET_PATH_ESCAPE", "Path traversal is not allowed.")
    candidate = root.joinpath(*candidate_rel.parts)
    try:
        candidate.resolve(strict=False).relative_to(root)
    except (ValueError, OSError):
        raise DatasetReviewError("DATASET_PATH_ESCAPE", "Path escapes the review root.") from None
    _reject_reparse(candidate)
    if candidate.suffix.casefold() not in allowed_extensions:
        raise DatasetReviewError("DATASET_TEXT_SCOPE_FORBIDDEN", "Only caption/text/metadata files may be changed.")
    if must_exist and not candidate.is_file():
        raise DatasetReviewError("DATASET_FILE_NOT_FOUND", "Caption file was not found.", status_code=404)
    return candidate


@dataclass(frozen=True)
class CaptionChange:
    relative_path: str
    before_text: str
    after_text: str
    before_hash: str
    after_hash: str
    diff: str
    reason: str
    source: str = "agent"

    @classmethod
    def build(cls, relative_path: str, before_text: str, after_text: str, *, reason: str = "", source: str = "agent") -> "CaptionChange":
        before_hash = _hash_bytes(before_text.encode("utf-8"))
        after_hash = _hash_bytes(after_text.encode("utf-8"))
        diff = "".join(unified_diff(before_text.splitlines(keepends=True), after_text.splitlines(keepends=True), fromfile=relative_path, tofile=relative_path))
        return cls(relative_path, before_text, after_text, before_hash, after_hash, diff, reason, source)

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return {"path": value.pop("relative_path"), "beforeText": value.pop("before_text"), "afterText": value.pop("after_text"), "beforeHash": value.pop("before_hash"), "afterHash": value.pop("after_hash"), **value}


@dataclass(frozen=True)
class CaptionChangeSet:
    change_set_id: str
    source_revision: str
    changes: tuple[CaptionChange, ...]
    change_set_hash: str
    created_at: str

    @classmethod
    def create(cls, changes: Iterable[CaptionChange], *, source_revision: str) -> "CaptionChangeSet":
        ordered = tuple(sorted(changes, key=lambda item: item.relative_path))
        if not ordered:
            raise DatasetReviewError("DATASET_CHANGESET_EMPTY", "At least one caption change is required.")
        if len({item.relative_path for item in ordered}) != len(ordered):
            raise DatasetReviewError("DATASET_CHANGESET_DUPLICATE_PATH", "A change set cannot contain duplicate paths.")
        if any(item.before_hash == item.after_hash for item in ordered):
            raise DatasetReviewError("DATASET_CHANGESET_NOOP", "A caption change must alter content.")
        payload = {"sourceRevision": source_revision, "changes": [item.as_dict() for item in ordered]}
        return cls(str(uuid.uuid4()), source_revision, ordered, _stable_hash(payload), datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {"changeSetId": self.change_set_id, "sourceRevision": self.source_revision, "changes": [change.as_dict() for change in self.changes], "changeSetHash": self.change_set_hash, "createdAt": self.created_at}


@dataclass(frozen=True)
class CaptionCommitResult:
    state: str
    change_set_hash: str
    committed: tuple[str, ...] = ()
    failed: tuple[dict[str, str], ...] = ()
    backup_dir: str | None = None
    restore_hashes: Mapping[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"state": self.state, "changeSetHash": self.change_set_hash, "committed": list(self.committed), "failed": list(self.failed), "backupDir": self.backup_dir, "restoreHashes": dict(self.restore_hashes)}


class CaptionOverlay:
    """Stage caption changes in a review overlay and host-commit atomically."""

    def __init__(self, dataset_root: str | Path, overlay_root: str | Path | None = None) -> None:
        self.dataset_root = _root(dataset_root)
        self.overlay_root = _root(overlay_root or (self.dataset_root / ".agent-dataset-review"), create=True)
        # The review overlay is host-owned and fixed to a reserved sibling of
        # the selected dataset.  An agent cannot nominate an arbitrary writable
        # tree, even when that tree happens to be inside the dataset.
        expected_overlay = (self.dataset_root / ".agent-dataset-review").resolve(strict=False)
        if self.overlay_root != expected_overlay:
            raise DatasetReviewError("DATASET_OVERLAY_INVALID", "Overlay must use the reserved review directory.")

    def _dataset_file(self, relative_path: str, *, must_exist: bool = True) -> Path:
        return _safe_relative(self.dataset_root, relative_path, allowed_extensions=ALLOWED_TEXT_EXTENSIONS, must_exist=must_exist)

    def _overlay_file(self, relative_path: str) -> Path:
        return _safe_relative(self.overlay_root, relative_path, allowed_extensions=ALLOWED_TEXT_EXTENSIONS, must_exist=False)

    def source_revision(self, paths: Iterable[str]) -> str:
        entries: list[dict[str, str | None]] = []
        for path in sorted(set(paths)):
            source = self._dataset_file(path, must_exist=True)
            data = source.read_bytes()
            entries.append({"path": path.replace("\\", "/"), "hash": _hash_bytes(data)})
        return _stable_hash(entries)

    def stage(self, relative_path: str, after_text: str, *, reason: str = "", source: str = "agent") -> CaptionChange:
        source_path = self._dataset_file(relative_path, must_exist=True)
        try:
            # Read bytes first so Windows newline translation cannot invalidate
            # the before-hash used for source-revision and TOCTOU checks.
            before_text = source_path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            raise DatasetReviewError("DATASET_TEXT_ENCODING_INVALID", "Caption text must be UTF-8.") from None
        if not isinstance(after_text, str):
            raise DatasetReviewError("DATASET_TEXT_INVALID", "Caption replacement must be text.")
        if not after_text.strip():
            raise DatasetReviewError("DATASET_CAPTION_DELETE_FORBIDDEN", "Empty caption replacement is not allowed.")
        if not after_text.strip():
            raise DatasetReviewError("DATASET_TEXT_EMPTY", "Empty caption replacement is not allowed.")
        change = CaptionChange.build(relative_path.replace("\\", "/"), before_text, after_text, reason=reason, source=source)
        overlay = self._overlay_file(relative_path)
        overlay.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(overlay, after_text.encode("utf-8"))
        return change

    def build_change_set(self, changes: Iterable[CaptionChange], *, source_revision: str | None = None) -> CaptionChangeSet:
        changes = tuple(changes)
        revision = source_revision or self.source_revision(change.relative_path for change in changes)
        return CaptionChangeSet.create(changes, source_revision=revision)

    def commit(self, change_set: CaptionChangeSet, *, confirmation_ticket: Mapping[str, Any] | None = None, backup_root: str | Path | None = None) -> CaptionCommitResult:
        ticket = confirmation_ticket or {}
        if ticket.get("state") != "approved":
            raise DatasetReviewError("DATASET_CONFIRMATION_REQUIRED", "An approved host confirmation ticket is required.", status_code=409)
        ticket_hash = ticket.get("changeSetHash") or ticket.get("change_set_hash")
        if ticket_hash != change_set.change_set_hash:
            raise DatasetReviewError("DATASET_CONFIRMATION_MISMATCH", "Confirmation ticket is not bound to this change set.", status_code=409)
        ticket_revision = ticket.get("sourceRevision") or ticket.get("source_revision")
        if ticket_revision is not None and ticket_revision != change_set.source_revision:
            raise DatasetReviewError("DATASET_CONFIRMATION_MISMATCH", "Confirmation ticket is not bound to this source revision.", status_code=409)
        current_revision = self.source_revision(change.relative_path for change in change_set.changes)
        if current_revision != change_set.source_revision:
            raise DatasetReviewError("DATASET_SOURCE_CHANGED", "Dataset text changed since the change set was created.", status_code=409)
        backup_dir = _root(backup_root or (self.overlay_root / "backups"), create=True)
        try:
            backup_dir.relative_to(self.overlay_root)
        except ValueError:
            raise DatasetReviewError("DATASET_BACKUP_INVALID", "Backup must be inside the review overlay.") from None
        backup_session = backup_dir / change_set.change_set_hash.removeprefix("sha256:")
        backup_session.mkdir(parents=True, exist_ok=True)
        committed: list[str] = []
        failed: list[dict[str, str]] = []
        try:
            for change in change_set.changes:
                target = self._dataset_file(change.relative_path, must_exist=True)
                current = target.read_bytes()
                if _hash_bytes(current) != change.before_hash:
                    raise DatasetReviewError("DATASET_SOURCE_CHANGED", "Dataset text changed during commit.", status_code=409)
                backup = backup_session / Path(change.relative_path)
                backup.parent.mkdir(parents=True, exist_ok=True)
                self._write_atomic(backup, current)
                self._write_atomic(target, change.after_text.encode("utf-8"))
                committed.append(change.relative_path)
        except DatasetReviewError as exc:
            # Restore all files already replaced, then report the conflict.
            for path in committed:
                backup = backup_session / Path(path)
                target = self._dataset_file(path, must_exist=True)
                if backup.exists():
                    self._write_atomic(target, backup.read_bytes())
            if exc.code == "DATASET_COMMIT_FAILED":
                return CaptionCommitResult(
                    "partial-failure",
                    change_set.change_set_hash,
                    (),
                    ({"code": exc.code, "reason": exc.message},),
                    str(backup_session),
                )
            raise
        except OSError as exc:
            for path in committed:
                backup = backup_session / Path(path)
                target = self._dataset_file(path, must_exist=True)
                if backup.exists():
                    self._write_atomic(target, backup.read_bytes())
            failed.append({"code": "DATASET_COMMIT_FAILED", "reason": str(exc)})
            committed = []
        return CaptionCommitResult("committed" if not failed else "partial-failure", change_set.change_set_hash, tuple(committed), tuple(failed), str(backup_session))

    def restore(self, commit: CaptionCommitResult | str | Path) -> CaptionCommitResult:
        backup_dir = Path(commit.backup_dir if isinstance(commit, CaptionCommitResult) else commit)
        try:
            backup_dir = backup_dir.resolve(strict=True)
            backup_dir.relative_to(self.overlay_root.resolve())
        except (OSError, ValueError):
            raise DatasetReviewError("DATASET_BACKUP_INVALID", "Backup must be inside the review overlay.") from None
        restored: list[str] = []
        failures: list[dict[str, str]] = []
        for backup in sorted(backup_dir.rglob("*")):
            if not backup.is_file():
                continue
            relative = backup.relative_to(backup_dir).as_posix()
            try:
                target = self._dataset_file(relative, must_exist=True)
                self._write_atomic(target, backup.read_bytes())
                restored.append(relative)
            except DatasetReviewError as exc:
                failures.append({"path": relative, "code": exc.code})
        hashes = {path: _hash_bytes(self._dataset_file(path, must_exist=True).read_bytes()) for path in restored}
        return CaptionCommitResult("restored" if not failures else "restore-partial", "", tuple(restored), tuple(failures), str(backup_dir), hashes)

    @staticmethod
    def _write_atomic(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
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
            raise DatasetReviewError("DATASET_COMMIT_FAILED", "Caption text could not be written.", details={"reason": str(exc)}) from None


__all__ = ["CaptionChange", "CaptionChangeSet", "CaptionCommitResult", "CaptionOverlay", "DatasetReviewError"]

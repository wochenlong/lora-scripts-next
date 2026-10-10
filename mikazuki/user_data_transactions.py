"""One root, process lock and recoverable transaction for user settings/presets.

Credential storage is deliberately excluded from the transaction allowlist.
"""
from __future__ import annotations

import base64
import copy
import json
import os
import re
import stat
import tempfile
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

MAX_BYTES = 1024 * 1024
JOURNAL = ".caption-preset-transaction.json"  # Recover journals from the old API too.
_ROOT = ContextVar("user_data_root", default=None)
_LOCK = threading.RLock()
_OWNER = threading.local()


class TransactionError(ValueError):
    pass


def resolve_root(root=None):
    configured = root if root is not None else _ROOT.get()
    if configured is None:
        configured = os.environ.get("MIKAZUKI_USER_DATA_ROOT", "").strip() or "user_data"
    path = Path(configured).expanduser()
    project = Path(__file__).resolve().parents[1]
    return (path if path.is_absolute() else project / path).absolute()


@contextmanager
def at_root(root):
    token = _ROOT.set(resolve_root(root))
    try:
        yield
    finally:
        _ROOT.reset(token)


def check_path(path, root=None):
    root = resolve_root(root)
    path = Path(path).absolute()
    try:
        path.relative_to(root)
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise TransactionError("User data path escapes user_data") from None
    current = path
    while True:
        if current.exists() or current.is_symlink():
            attributes = getattr(current.lstat(), "st_file_attributes", 0)
            if current.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise TransactionError("User data cannot use symbolic links or junctions")
        if current == root:
            break
        current = current.parent


def read_bytes(path):
    check_path(path)
    if not path.exists():
        return None
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise TransactionError("User data file is too large")
    return raw


def read_json(path, default):
    raw = read_bytes(path)
    if raw is None:
        return copy.deepcopy(default)
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError, RecursionError):
        raise TransactionError(f"User data is unreadable: {path.name}") from None


def json_bytes(value):
    try:
        raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, UnicodeError, RecursionError):
        raise TransactionError("User data must contain valid bounded JSON") from None
    if len(raw) > MAX_BYTES:
        raise TransactionError("User data file is too large")
    return raw


def atomic_bytes(path, value):
    check_path(path)
    if value is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".user-data-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        check_path(path)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _allowed(relative):
    return relative in {"settings.json", "settings.json.bak"} or bool(
        re.fullmatch(r"presets/[A-Za-z0-9][A-Za-z0-9._-]*\.json(?:\.bak)?", relative)
        or re.fullmatch(r"migrations/caption-presets/[a-f0-9]{64}\.source\.json", relative))


def _decode(value):
    if value is None:
        return None
    try:
        if not isinstance(value, str):
            raise ValueError()
        return base64.b64decode(value, validate=True)
    except ValueError:
        raise TransactionError("Caption preset transaction is invalid") from None


def recover(write=None):
    write = write or atomic_bytes
    journal_path = resolve_root() / JOURNAL
    # A whole 24-preset journal can exceed the per-record bound.
    check_path(journal_path)
    if not journal_path.exists():
        return
    if journal_path.stat().st_size > MAX_BYTES * 64:
        raise TransactionError("Caption preset transaction is too large")
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, RecursionError):
        raise TransactionError("Caption preset transaction is invalid") from None
    if not isinstance(journal, dict) or journal.get("schema_version") != 1 or journal.get("state") not in {"prepared", "committed"} or not isinstance(journal.get("files"), list):
        raise TransactionError("Caption preset transaction is invalid")
    files, seen = [], set()
    for entry in journal["files"]:
        if not isinstance(entry, dict):
            raise TransactionError("Caption preset transaction is invalid")
        relative = entry.get("path")
        if not isinstance(relative, str) or not _allowed(relative) or relative.casefold() in seen:
            raise TransactionError("Caption preset transaction path is invalid")
        seen.add(relative.casefold())
        target = resolve_root() / relative
        check_path(target)
        files.append((target, _decode(entry.get("before")), _decode(entry.get("after"))))
    if any(read_bytes(target) not in (before, after) for target, before, after in files):
        raise TransactionError("Caption preset recovery conflict")
    desired_index = 1 if journal["state"] == "prepared" else 2
    for entry in reversed(files):
        if read_bytes(entry[0]) != entry[desired_index]:
            write(entry[0], entry[desired_index])
    journal_path.unlink()


@contextmanager
def guard(root=None, write=None, create=True):
    with at_root(resolve_root(root)), _LOCK:
        resolved = resolve_root()
        owned = getattr(_OWNER, "roots", set())
        if str(resolved) in owned:
            yield
            return
        check_path(resolved)
        if not create and not resolved.exists():
            yield
            return
        resolved.mkdir(parents=True, exist_ok=True)
        lock_path = resolved / ".write.lock"
        check_path(lock_path)
        with lock_path.open("a+b") as stream:
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"0")
                stream.flush()
            deadline = time.monotonic() + 10
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
                        raise TransactionError("User data is busy; retry saving") from None
                    time.sleep(.025)
            _OWNER.roots = owned | {str(resolved)}
            try:
                recover(write)
                yield
            finally:
                _OWNER.roots = owned
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def transaction(changes, write=None):
    write = write or atomic_bytes
    files = []
    for target, value in changes.items():
        relative = target.relative_to(resolve_root()).as_posix()
        if not _allowed(relative):
            raise TransactionError("Caption preset transaction path is invalid")
        if value is not None and len(value) > MAX_BYTES:
            raise TransactionError("User data file is too large")
        before = read_bytes(target)
        encode = lambda item: None if item is None else base64.b64encode(item).decode("ascii")
        files.append({"path": relative, "before": encode(before), "after": encode(value)})
    if all(item["before"] == item["after"] for item in files):
        return
    path = resolve_root() / JOURNAL
    journal = {"schema_version": 1, "state": "prepared", "files": files}
    raw = lambda: (json.dumps(journal, ensure_ascii=False) + "\n").encode("utf-8")
    write(path, raw())
    try:
        for target, value in changes.items():
            write(target, value)
        journal["state"] = "committed"
        write(path, raw())
    except BaseException:
        recover(write)
        raise
    path.unlink()

"""同文件写入协调与非任务 caption 写入的故障补偿。

Editor、原生 Tag、任务提交和回滚共用路径锁。锁仅保护本服务的
写入者；外部进程仍由提交前后的内容哈希检查保护。
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from functools import wraps
import hashlib
import os
import sqlite3
from pathlib import Path
import tempfile
import threading
from weakref import WeakValueDictionary

_LOCKS = WeakValueDictionary()
_LOCKS_GUARD = threading.Lock()


def path_key(path):
    return os.path.normcase(str(Path(path).resolve()))


@contextmanager
def caption_file_lock(path):
    key = path_key(path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
    with lock:
        yield


@contextmanager
def caption_files_lock(paths):
    # Stable ordering prevents two multi-file operations deadlocking.
    with ExitStack() as stack:
        for path in sorted({path_key(path) for path in paths}):
            stack.enter_context(caption_file_lock(path))
        yield


def locked_caption(function):
    @wraps(function)
    def wrapped(path, *args, **kwargs):
        with caption_file_lock(path):
            return function(path, *args, **kwargs)
    return wrapped


def _hash_bytes(content):
    return hashlib.sha256(content).hexdigest() if content is not None else None


def replace_caption_bytes(path, content, *, expected_sha256):
    from .caption_job import CaptionWriteConflict, caption_sha256
    path = Path(path)
    with caption_file_lock(path):
        if path.is_symlink() or caption_sha256(path) != expected_sha256:
            raise CaptionWriteConflict("caption changed before commit")
        if content is None:
            path.unlink(missing_ok=True)
            return None
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if path.is_symlink() or caption_sha256(path) != expected_sha256:
                raise CaptionWriteConflict("caption changed during commit")
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return _hash_bytes(content)


def recover_caption_write(store, path):
    """Uncommitted editor/legacy writes roll back, never overwrite external edits."""
    from .caption_job import CaptionPersistenceError, CaptionWriteConflict, caption_sha256
    with caption_file_lock(path):
        intent = store.get_write_intent(path)
        if intent is None:
            return
        if _hash_bytes(intent["before_content"]) != intent["before_hash"]:
            raise CaptionPersistenceError("caption 恢复备份校验失败；原文未修改")
        current = caption_sha256(Path(path))
        if current == intent["before_hash"]:
            pass
        elif current == intent["after_hash"]:
            # A scan can encounter an interrupted editor write after restart.
            # Restoring bytes is still a mutation and must respect training use.
            from mikazuki.datasets.inuse import ensure_path_not_in_use
            ensure_path_not_in_use(str(path))
            replace_caption_bytes(path, intent["before_content"], expected_sha256=current)
        else:
            raise CaptionWriteConflict("caption has an unresolved write and an external change")
        try:
            store.restore_write_intent(path, intent["before_record"])
        except (OSError, sqlite3.Error):
            raise CaptionPersistenceError("无法恢复 caption 来源，请检查数据库后重试") from None


def commit_caption_write(store, path, content, *, expected_sha256, caption_format, tags=None):
    """Durable write-ahead compensation; provenance + intent removal commit together."""
    import sqlite3
    from .caption_job import CaptionPersistenceError, CaptionWriteConflict, caption_sha256
    path = Path(path)
    with caption_file_lock(path):
        recover_caption_write(store, path)
        if path.is_symlink() or caption_sha256(path) != expected_sha256:
            raise CaptionWriteConflict("caption changed before editor write")
        before = path.read_bytes() if path.is_file() else None
        if _hash_bytes(before) != expected_sha256:
            raise CaptionWriteConflict("caption changed before editor backup")
        after_hash = _hash_bytes(content)
        try:
            store.prepare_write_intent(path, before, expected_sha256, after_hash)
        except (sqlite3.Error, OSError):
            raise CaptionPersistenceError("无法保存 caption 写入记录；原文未修改") from None
        try:
            replace_caption_bytes(path, content, expected_sha256=expected_sha256)
            store.finish_write_intent(path, after_hash, caption_format, tags)
        except Exception as error:
            # Also handles failures before the replacement. Recovery recognizes
            # either hash, and preserves an external writer as a conflict.
            try:
                recover_caption_write(store, path)
            except Exception:
                raise CaptionPersistenceError("caption 写入未完成；恢复记录已保留，请检查存储后重试") from error
            if isinstance(error, (sqlite3.Error, OSError)):
                raise CaptionPersistenceError("caption 保存失败；已恢复保存前原文，请检查存储后重试") from None
            raise
        return after_hash

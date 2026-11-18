"""Serialize runtime mutation across requests and processes."""
import os
import threading
from contextlib import contextmanager
from pathlib import Path

request_lock = threading.RLock()


@contextmanager
def environment_lock(root):
    path = Path(root).parent / ".kohaku-moss.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            if not handle.read(1):
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            def lock():
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

            def unlock():
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def lock():
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

            def unlock():
                fcntl.flock(handle, fcntl.LOCK_UN)
        try:
            lock()
        except OSError as exc:
            raise ValueError("KohakuMossTrainer 环境正在使用中。") from exc
        try:
            yield
        finally:
            handle.seek(0)
            unlock()

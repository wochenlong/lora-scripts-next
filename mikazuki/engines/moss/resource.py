"""Serialize install requests and lock the runtime across processes."""
from contextlib import contextmanager
from pathlib import Path
import os
import threading

request_lock = threading.RLock()


@contextmanager
def environment_lock(root):
    # Kept outside the extension so uninstall cannot delete a held lock.
    path = Path(root).parent / ".moss.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            def acquire():
                handle.seek(0)
                if not handle.read(1):
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

            def release():
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            def acquire():
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

            def release():
                fcntl.flock(handle, fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as exc:
            raise ValueError("MOSS 环境正在使用中，请等待当前任务结束。") from exc
        try:
            yield
        finally:
            release()

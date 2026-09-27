"""Serialize requests and protect the environment across worker processes."""
from contextlib import contextmanager
from pathlib import Path
import os
import threading

request_lock = threading.RLock()


@contextmanager
def environment_lock(root):
    # Outside the environment so repair/uninstall cannot delete the held lock.
    path = Path(root).parent / '.diffsynth.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as file:
        file.seek(0)
        if os.name == 'nt':
            import msvcrt
            if not file.read(1):
                file.write(b'0')
                file.flush()
            file.seek(0)
            lock = lambda: msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            unlock = lambda: msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            lock = lambda: fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            unlock = lambda: fcntl.flock(file, fcntl.LOCK_UN)
        try:
            lock()
        except OSError as exc:
            raise ValueError('DiffSynth 环境正在使用中，请等待当前任务结束。') from exc
        try:
            yield
        finally:
            file.seek(0)
            unlock()

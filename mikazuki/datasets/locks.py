from __future__ import annotations

import threading
from contextlib import contextmanager

from fastapi import HTTPException

ACQUIRE_TIMEOUT_SECONDS = 5.0

_locks: dict[str, threading.RLock] = {}
_guard = threading.Lock()


def lock_for(dataset_name: str) -> threading.RLock:
    with _guard:
        return _locks.setdefault(dataset_name, threading.RLock())


@contextmanager
def dataset_operation(dataset_name: str):
    lock = lock_for(dataset_name)
    if not lock.acquire(timeout=ACQUIRE_TIMEOUT_SECONDS):
        raise HTTPException(
            status_code=409,
            detail=f"another operation is in progress for dataset '{dataset_name}'",
        )
    try:
        yield
    finally:
        lock.release()

"""Natural-language translation provider slots shared across threads and loops."""
from __future__ import annotations

import asyncio
import os
import threading
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from .config import DEFAULT_CAPTION_TRANSLATION_SETTINGS, validate_caption_translation_settings


@dataclass(eq=False)
class _Ticket:
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future


class CaptionTranslationGate:
    def __init__(self):
        self._lock = threading.RLock()
        self._limit = DEFAULT_CAPTION_TRANSLATION_SETTINGS["concurrency"]
        self._active = set()
        self._waiting = deque()

    def snapshot(self):
        with self._lock:
            return {"active": len(self._active), "waiting": len(self._waiting), "concurrency": self._limit}

    def configure(self, limit_getter):
        with self._lock:
            self._limit = limit_getter()
            self._advance_locked()

    def _advance_locked(self):
        # Lowering the limit lets running providers finish, then drains at the
        # new limit. Increasing it immediately wakes waiting requests.
        while len(self._active) < self._limit and self._waiting:
            ticket = self._waiting.popleft()
            if ticket.future.cancelled() or ticket.loop.is_closed():
                continue
            self._active.add(ticket)

            def granted(item=ticket):
                if item.future.done():
                    self._release(item)
                else:
                    item.future.set_result(None)

            try:
                ticket.loop.call_soon_threadsafe(granted)
            except RuntimeError:
                self._active.discard(ticket)

    def _release(self, ticket):
        with self._lock:
            self._active.discard(ticket)
            try:
                self._waiting.remove(ticket)
            except ValueError:
                pass
            self._advance_locked()

    async def acquire(self, limit_getter):
        loop = asyncio.get_running_loop()
        ticket = _Ticket(loop, loop.create_future())
        with self._lock:
            # Read the authoritative current configuration under the gate's
            # lock, so a stale translation snapshot cannot restore an old limit.
            self._limit = limit_getter()
            self._waiting.append(ticket)
            self._advance_locked()
        try:
            await ticket.future
            return ticket
        except BaseException:
            self._release(ticket)
            raise

    @asynccontextmanager
    async def slot(self, limit_getter):
        ticket = await self.acquire(limit_getter)
        try:
            yield
        finally:
            self._release(ticket)


_GATES = {}
_GATES_LOCK = threading.Lock()


def translation_gate(service):
    store = getattr(service, "config_store", None)
    path = getattr(store, "path", None)
    key = ("store", os.path.normcase(str(Path(path).resolve()))) if path is not None else ("service", id(service))
    with _GATES_LOCK:
        return _GATES.setdefault(key, CaptionTranslationGate())


def current_concurrency(service):
    config = service.config(masked=False)
    return validate_caption_translation_settings(config.get("caption_translation", DEFAULT_CAPTION_TRANSLATION_SETTINGS))["concurrency"]


def refresh_translation_gate(service):
    translation_gate(service).configure(lambda: current_concurrency(service))

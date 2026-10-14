"""跨 Caption 工作线程/事件循环的共享 FIFO：执行 1 项，等待最多 2 项。"""
from __future__ import annotations

import asyncio
import threading
import uuid
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass

from .http import LLMRequestError


@dataclass
class _Ticket:
    token: str
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future


class LocalRequestScheduler:
    def __init__(self, max_waiting=2):
        self.max_waiting = max_waiting
        self._lock = threading.RLock()
        self._waiting = deque()
        self._active = None
        self._paused = False

    def snapshot(self):
        with self._lock:
            return {"active": int(self._active is not None), "waiting": len(self._waiting),
                    "max_active": 1, "max_waiting": self.max_waiting, "paused": self._paused}

    def is_busy(self):
        with self._lock:
            return self._active is not None or bool(self._waiting)

    @contextmanager
    def idle_guard(self):
        """停止/更换运行时时原子阻断新请求；忙时拒绝，绝不误取消生成。"""
        with self._lock:
            if self._paused or self._active is not None or self._waiting:
                raise LLMRequestError("本地模型正在处理请求，请等待完成后再停止或重新安装", "llm_local_busy", retryable=True)
            self._paused = True
        try:
            yield
        finally:
            with self._lock:
                self._paused = False

    def _advance_locked(self):
        while self._waiting:
            ticket = self._waiting.popleft()
            if ticket.future.cancelled() or ticket.loop.is_closed():
                continue
            self._active = ticket

            def granted(item=ticket):
                if not item.future.done():
                    item.future.set_result(None)

            try:
                ticket.loop.call_soon_threadsafe(granted)
            except RuntimeError:
                self._active = None
                continue
            return
        self._active = None

    def _release(self, ticket):
        with self._lock:
            if self._active is ticket:
                self._active = None
                self._advance_locked()
            else:
                try:
                    self._waiting.remove(ticket)
                except ValueError:
                    pass

    async def acquire(self):
        loop = asyncio.get_running_loop()
        ticket = _Ticket(uuid.uuid4().hex, loop, loop.create_future())
        with self._lock:
            if self._paused:
                raise LLMRequestError("本地模型生命周期操作正在进行", "llm_local_busy", retryable=True)
            if self._active is None:
                self._active = ticket
                return ticket
            if len(self._waiting) >= self.max_waiting:
                raise LLMRequestError("本地模型等待队列已满，请稍后重试", "llm_local_queue_full", retryable=True)
            self._waiting.append(ticket)
        try:
            await ticket.future
            return ticket
        except BaseException:
            self._release(ticket)
            raise

    @asynccontextmanager
    async def slot(self):
        ticket = await self.acquire()
        try:
            yield
        finally:
            self._release(ticket)


shared_local_scheduler = LocalRequestScheduler()


def snapshot():
    return shared_local_scheduler.snapshot()


def is_busy():
    return shared_local_scheduler.is_busy()


@asynccontextmanager
async def local_request_slot(profile):
    source = profile.get("source") if isinstance(profile, dict) else profile.source
    if source == "managed-local":
        async with shared_local_scheduler.slot():
            yield
    else:
        yield

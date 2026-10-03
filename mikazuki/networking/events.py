"""Task-local transport events; callbacks must not break installations."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging

_sink = ContextVar("download_event_sink", default=None)
logger = logging.getLogger(__name__)


def emit(**event):
    sink = _sink.get()
    if sink:
        try:
            sink(event)
        except Exception:
            logger.debug("Download event callback failed", exc_info=False)


@contextmanager
def observe(sink):
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)

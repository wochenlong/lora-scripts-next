"""Background install operations with progress reporting.

The install endpoint no longer blocks on package acquisition + extraction.
It starts an :class:`InstallOperation` (a daemon worker thread) and returns
an operation id immediately (HTTP 202).  Clients observe the operation via
the snapshot endpoint (polling) or the SSE stream endpoint.

Phases (in order):

    acquiring      package copy / download (byte progress available)
    verifying      trust + size + sha256 + manifest validation
    extracting     zip extraction into the staging directory
    health_check   packaged health check against the staging copy
    committing     registry commit + runtime switch (if upgrading)
    done           terminal (state carries the outcome)

Cancellation is cooperative: the worker checks the cancel flag between
acquire chunks and at each phase boundary.  A cancelled operation leaves
no installed version behind (manager.install cleans its staging).
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable

# Machine-facing phase ids.  The frontend translates these for display.
PHASE_ACQUIRING = "acquiring"
PHASE_VERIFYING = "verifying"
PHASE_EXTRACTING = "extracting"
PHASE_HEALTH_CHECK = "health_check"
PHASE_COMMITTING = "committing"
PHASE_DONE = "done"

STATE_RUNNING = "running"
STATE_SUCCEEDED = "succeeded"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"

TERMINAL_STATES = frozenset({STATE_SUCCEEDED, STATE_FAILED, STATE_CANCELLED})

# Kept in-memory; the most recent terminal operations are retained for late
# subscribers.  Older ones are pruned.
_TERMINAL_RETENTION = 32
_MIN_PROGRESS_TICK_S = 0.25


class OperationCancelled(Exception):
    """Raised inside an install pipeline when the user cancels the operation."""


class InstallOperationConflict(Exception):
    """A second install is already running for the same plugin."""


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class InstallOperation:
    """One background install with a thread-safe, snapshot-able state."""

    def __init__(self, operation_id: str, plugin_id: str, version: str) -> None:
        self.id = operation_id
        self.plugin_id = plugin_id
        self.version = version
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._last_progress_push = 0.0
        self.state = STATE_RUNNING
        self.phase = PHASE_ACQUIRING
        self.message = ""
        self.current = 0
        self.total = 0
        self.error_code: str | None = None
        self.error_message: str | None = None
        self.status: dict[str, Any] | None = None
        self.started_at = _now_iso()
        self.finished_at: str | None = None

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    @property
    def running(self) -> bool:
        return self.state == STATE_RUNNING

    def request_cancel(self) -> bool:
        """Return False when the operation already reached a terminal state."""
        with self._lock:
            if self.state != STATE_RUNNING:
                return False
            self._cancel.set()
            return True

    def report_phase(self, phase: str) -> None:
        with self._lock:
            if self.state != STATE_RUNNING:
                return
            self.phase = phase

    def report_progress(self, phase: str, current: int, total: int, *, force: bool = False) -> None:
        """Coalesce byte-progress updates to ~4/second per operation."""
        now = time.monotonic()
        if not force and now - self._last_progress_push < _MIN_PROGRESS_TICK_S:
            # Keep the latest value even when coalescing the *push* below.
            with self._lock:
                if self.state == STATE_RUNNING:
                    self.phase = phase
                    self.current = current
                    self.total = total
            return
        self._last_progress_push = now
        with self._lock:
            if self.state != STATE_RUNNING:
                return
            self.phase = phase
            self.current = current
            self.total = total

    def finish_success(self, status: dict[str, Any]) -> None:
        with self._lock:
            if self.state != STATE_RUNNING:
                return
            self.state = STATE_SUCCEEDED
            self.phase = PHASE_DONE
            self.current = self.total
            self.status = status
            self.finished_at = _now_iso()

    def finish_failure(self, error_code: str, error_message: str) -> None:
        with self._lock:
            if self.state != STATE_RUNNING:
                return
            self.state = STATE_FAILED
            self.phase = PHASE_DONE
            self.error_code = error_code
            self.error_message = error_message
            self.finished_at = _now_iso()

    def finish_cancelled(self) -> None:
        with self._lock:
            if self.state != STATE_RUNNING:
                return
            self.state = STATE_CANCELLED
            self.phase = PHASE_DONE
            self.error_code = "MARKETPLACE_OPERATION_CANCELLED"
            self.error_message = "The plugin installation was cancelled."
            self.finished_at = _now_iso()

    def percent(self) -> float | None:
        if not self.total or self.total <= 0:
            return None
        return round(min(self.current, self.total) / self.total * 100, 1)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "operationId": self.id,
                "pluginId": self.plugin_id,
                "version": self.version,
                "state": self.state,
                "phase": self.phase,
                "progress": {
                    "current": self.current,
                    "total": self.total,
                    "percent": self.percent(),
                },
                "errorCode": self.error_code,
                "errorMessage": self.error_message,
                "status": self.status,
                "startedAt": self.started_at,
                "finishedAt": self.finished_at,
            }


def classify_install_error(exc: Exception) -> tuple[str, str]:
    """Map pipeline exceptions to (error_code, public_message)."""
    from .catalog import CatalogError
    from .trust import TrustError

    if isinstance(exc, CatalogError):
        return exc.code, exc.public_message
    if isinstance(exc, TrustError):
        return "MARKETPLACE_TRUST_FAILED", "Marketplace package trust verification failed."
    if isinstance(exc, PermissionError):
        return "MARKETPLACE_PERMISSION_REJECTED", str(exc)
    if isinstance(exc, (ValueError, OSError, RuntimeError)):
        return "MARKETPLACE_INSTALL_FAILED", str(exc)
    return "MARKETPLACE_INSTALL_FAILED", f"Unexpected error: {exc!r}"


class InstallOperationRegistry:
    """Holds live + recent install operations and drives their worker threads."""

    def __init__(self, pipeline: Callable[[InstallOperation, Any, set[str]], None]) -> None:
        # pipeline(op, entry, approved_permissions): must run to completion and
        # finish the operation via op.finish_success / finish_failure; raising
        # OperationCancelled or any other exception is handled by the worker.
        self._pipeline = pipeline
        self._operations: dict[str, InstallOperation] = {}
        self._lock = threading.Lock()

    def start(self, plugin_id: str, entry: Any, approved_permissions: set[str]) -> InstallOperation:
        operation = InstallOperation(uuid.uuid4().hex, plugin_id, entry.latest_version)
        with self._lock:
            for existing in self._operations.values():
                if existing.plugin_id == plugin_id and existing.state == STATE_RUNNING:
                    raise InstallOperationConflict(
                        f"an install is already running for {plugin_id}: {existing.id}"
                    )
            self._operations[operation.id] = operation
            self._prune_locked()
        worker = threading.Thread(
            target=self._run,
            args=(operation, entry, approved_permissions),
            name=f"plugin-install-{operation.id[:8]}",
            daemon=True,
        )
        worker.start()
        return operation

    def _run(self, operation: InstallOperation, entry: Any, approved_permissions: set[str]) -> None:
        try:
            self._pipeline(operation, entry, approved_permissions)
        except OperationCancelled:
            operation.finish_cancelled()
        except Exception as exc:  # noqa: BLE001 — surfaced as the operation error
            code, message = classify_install_error(exc)
            operation.finish_failure(code, message)
        if operation.running:
            # A pipeline that returns without finishing its operation is a bug;
            # never leave the client waiting on a running state.
            operation.finish_failure("MARKETPLACE_INSTALL_INCOMPLETE", "The install pipeline did not complete.")

    def get(self, plugin_id: str, operation_id: str) -> InstallOperation | None:
        with self._lock:
            operation = self._operations.get(operation_id)
        if operation is None or operation.plugin_id != plugin_id:
            return None
        return operation

    def active(self, plugin_id: str) -> InstallOperation | None:
        """The running install operation for a plugin, if any.

        Used to (a) attach a repeated install click to the in-flight work
        instead of failing it, and (b) surface progress on plugin status so
        a client that left the page (or reloaded) can re-attach its UI.
        """
        with self._lock:
            for operation in self._operations.values():
                if operation.plugin_id == plugin_id and operation.state == STATE_RUNNING:
                    return operation
        return None

    def active_plugin_ids(self) -> list[str]:
        """Plugins with a running install operation (including not-yet-
        installed ones, which list_statuses() would otherwise omit)."""
        with self._lock:
            return sorted(
                {op.plugin_id for op in self._operations.values() if op.state == STATE_RUNNING}
            )

    def _prune_locked(self) -> None:
        terminal = [
            op for op in self._operations.values() if op.state in TERMINAL_STATES
        ]
        terminal.sort(key=lambda op: op.finished_at or "")
        while len(terminal) > _TERMINAL_RETENTION:
            oldest = terminal.pop(0)
            self._operations.pop(oldest.id, None)

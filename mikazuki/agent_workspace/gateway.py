from __future__ import annotations

import inspect
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

from .errors import AgentDomainError
from .redaction import redact


@dataclass(frozen=True)
class ToolMetadata:
    name: str
    version: str = "v1"
    purpose: str = ""
    permission: str = "agent.read"
    side_effect: str = "read"  # read | write | external
    deadline_ms: int = 10_000
    limits: dict[str, int] = field(default_factory=dict)
    redaction: str = "configured"
    audit: bool = True
    expiry_seconds: int = 300

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "purpose": self.purpose,
            "permission": self.permission,
            "sideEffect": self.side_effect,
            "deadlineMs": self.deadline_ms,
            "limits": dict(self.limits),
            "redaction": self.redaction,
            "audit": self.audit,
            "expirySeconds": self.expiry_seconds,
        }


@dataclass(frozen=True)
class ToolEnvelope:
    request_id: str
    method: str
    session_id: str
    params: dict[str, Any]
    issued_at: float
    deadline_ms: int
    confirmation_ticket_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "method": self.method,
            "sessionId": self.session_id,
            "params": redact(self.params),
            "issuedAt": self.issued_at,
            "deadlineMs": self.deadline_ms,
            "confirmationTicketId": self.confirmation_ticket_id,
        }


ToolHandler = Callable[[ToolEnvelope], Any | Awaitable[Any]]


class ToolRegistry:
    """Small host-domain registry; unknown methods fail with a stable code."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolMetadata, ToolHandler]] = {}

    def register(self, metadata: ToolMetadata, handler: ToolHandler) -> None:
        if not metadata.name or metadata.name in self._tools:
            raise ValueError("tool metadata name must be unique")
        if metadata.side_effect not in {"read", "write", "external"}:
            raise ValueError("tool side_effect must be read, write, or external")
        if metadata.deadline_ms < 1 or metadata.deadline_ms > 120_000:
            raise ValueError("tool deadline is outside the supported range")
        self._tools[metadata.name] = (metadata, handler)

    def unregister(self, method: str) -> None:
        self._tools.pop(method, None)

    def metadata(self) -> list[dict[str, Any]]:
        return [self._tools[key][0].as_dict() for key in sorted(self._tools)]

    async def invoke(self, envelope: ToolEnvelope) -> Any:
        registered = self._tools.get(envelope.method)
        if registered is None:
            raise AgentDomainError("TOOL_NOT_FOUND", "The requested Tool is not available.", status_code=404)
        metadata, handler = registered
        elapsed = (time.monotonic() - envelope.issued_at) * 1000
        if elapsed > metadata.deadline_ms:
            raise AgentDomainError("TOOL_DEADLINE_EXCEEDED", "The Tool request deadline has expired.", status_code=408, retryable=True)
        try:
            result = handler(envelope)
            if inspect.isawaitable(result):
                result = await result
            return redact(result)
        except AgentDomainError:
            raise
        except Exception as exc:
            raise AgentDomainError("TOOL_FAILED", "The Tool request failed.", details={"reason": str(exc)}) from None

    @staticmethod
    def envelope(method: str, params: dict[str, Any], *, session_id: str, deadline_ms: int = 10_000, request_id: str | None = None, confirmation_ticket_id: str | None = None) -> ToolEnvelope:
        if not isinstance(params, dict):
            raise AgentDomainError("TOOL_PARAMS_INVALID", "Tool parameters must be an object.")
        return ToolEnvelope(
            request_id=request_id or str(uuid.uuid4()),
            method=method,
            session_id=session_id,
            params=params,
            issued_at=time.monotonic(),
            deadline_ms=deadline_ms,
            confirmation_ticket_id=confirmation_ticket_id,
        )


__all__ = ["ToolEnvelope", "ToolMetadata", "ToolRegistry"]

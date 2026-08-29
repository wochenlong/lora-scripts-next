from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Stable, redacted error identifiers exposed to the host/tool gateway."""

    INVALID_QUERY = "AGENT_SKILL_INVALID_QUERY"
    INVALID_RECORD = "AGENT_SKILL_INVALID_RECORD"
    OFFICIAL_SOURCE_REQUIRED = "AGENT_SKILL_OFFICIAL_SOURCE_REQUIRED"
    NETWORK_ERROR = "AGENT_SKILL_NETWORK_ERROR"
    RATE_LIMITED = "AGENT_SKILL_RATE_LIMITED"
    RESPONSE_INVALID = "AGENT_SKILL_RESPONSE_INVALID"
    SKILL_INVALID = "AGENT_SKILL_INVALID"
    SKILL_NOT_PUBLISHABLE = "AGENT_SKILL_NOT_PUBLISHABLE"


class AgentSkillError(ValueError):
    def __init__(self, code: ErrorCode | str, message: str, *, retry_after: float | None = None):
        self.code = code.value if isinstance(code, ErrorCode) else str(code)
        self.retry_after = retry_after
        # Never include request headers, URLs with query tokens, or response bodies.
        super().__init__(message)


__all__ = ["AgentSkillError", "ErrorCode"]

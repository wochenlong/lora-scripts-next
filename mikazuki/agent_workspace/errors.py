from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentDomainError(Exception):
    """Stable public error used by workspace/artifact Tool handlers."""

    code: str
    message: str
    status_code: int = 400
    retryable: bool = False
    details: dict | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    @property
    def public_message(self) -> str:
        return self.message

    def as_dict(self) -> dict:
        result = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details:
            result["details"] = self.details
        return result


__all__ = ["AgentDomainError"]

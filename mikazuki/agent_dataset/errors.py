from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DatasetReviewError(Exception):
    """Stable, non-sensitive host error for dataset review operations."""

    code: str
    message: str
    status_code: int = 400
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}

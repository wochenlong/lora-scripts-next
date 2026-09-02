"""Host-owned dataset review and caption change services.

The module deliberately has no model implementation.  Deterministic inventory
is local and read-only; multimodal review accepts an already selected remote
model capability and a caller supplied remote reviewer.  Caption edits are
staged in an isolated overlay and can only be committed after an explicit,
hash-bound approval ticket.
"""

from .audit import (
    ActiveModelCapability,
    DatasetInventory,
    DatasetReviewReport,
    ImageReviewResult,
    InventoryItem,
    inventory_dataset,
    review_images,
    select_review_sample,
)
from .changes import (
    CaptionChange,
    CaptionChangeSet,
    CaptionCommitResult,
    CaptionOverlay,
    DatasetReviewError,
)
from .remote_reviewer import BridgeVisionReviewer, get_configured_reviewer


class ImageCapability:
    """Compatibility view for callers that only need image availability."""

    def __init__(self, model_id: str, supports_image: bool, reason: str | None = None) -> None:
        self.model_id = model_id
        self.supports_image = supports_image
        self.reason = reason

    @classmethod
    def from_active_model(cls, metadata: dict | None) -> "ImageCapability":
        metadata = metadata or {}
        model_id = str(metadata.get("modelId") or metadata.get("model_id") or "active-remote-model")
        supports = bool(metadata.get("supportsImage") or metadata.get("image") or metadata.get("vision"))
        return cls(model_id, supports, None if supports else "MODEL_CAPABILITY_UNAVAILABLE")

__all__ = [
    "ActiveModelCapability",
    "BridgeVisionReviewer",
    "CaptionChange",
    "CaptionChangeSet",
    "CaptionCommitResult",
    "CaptionOverlay",
    "DatasetInventory",
    "DatasetReviewError",
    "DatasetReviewReport",
    "ImageReviewResult",
    "ImageCapability",
    "InventoryItem",
    "inventory_dataset",
    "review_images",
    "select_review_sample",
]

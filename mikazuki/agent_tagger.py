from __future__ import annotations

"""Host-owned adapter for the tagger batch job exposed to the Pi Agent.

The tagger in ``mikazuki.tagger`` is a *singleton* background job (one job at a
time) whose progress is tracked by the global ``tagger_progress`` object and
whose work runs in ``run_interrogate_job``.  This module gives that job stable
Host-Tool semantics for the optional Pi Agent: model validation, parameter
validation, a busy guard, a cooperative cancel and progress snapshots.

Domain rules (ONNX models, download, progress bookkeeping) stay in
``mikazuki.tagger``; this layer only translates the Tool boundary.  The job is
run on a daemon thread so the async dispatcher is never blocked for the
duration of tagging.

Note: :class:`TaggerJobRequest` intentionally mirrors the WebUI model
``mikazuki.app.models.TaggerInterrogateRequest`` field-for-field (same names and
defaults) so both entry points drive ``run_interrogate_job`` identically.  It is
defined here rather than imported from ``mikazuki.app`` to keep this domain
module free of the HTTP layer (and to avoid the app startup import cycle).
``run_interrogate_job`` consumes the request by attribute access only.
"""

import threading
from dataclasses import dataclass, field
from typing import Any

from mikazuki.tagger.interrogator import available_interrogators
from mikazuki.tagger.jobs import run_interrogate_job
from mikazuki.tagger.progress import tagger_progress

_DEFAULT_MODEL = "wd14-convnextv2-v2"
_DEFAULT_UNDERSCORE_EXCLUDES = (
    "0_0, (o)_(o), +_+, +_-, ._., <o>_<o>, <|>_<|>, =_=, >_<, 3_3, 6_9, >_o, @_@, ^_^, "
    "o_o, u_u, x_x, |_|, ||_||"
)


@dataclass
class TaggerToolError(Exception):
    """Stable, non-sensitive host error for tagger Tool operations."""

    code: str
    message: str
    status_code: int = 400
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


@dataclass
class TaggerJobRequest:
    """Request payload for a batch tagging job.

    Mirrors ``mikazuki.app.models.TaggerInterrogateRequest`` — keep the two in
    sync if either changes.
    """

    path: str
    interrogator_model: str = _DEFAULT_MODEL
    threshold: float = 0.35
    character_threshold: float = 0.6
    add_rating_tag: bool = False
    add_model_tag: bool = False
    additional_tags: str = ""
    exclude_tags: str = ""
    escape_tag: bool = True
    batch_input_recursive: bool = False
    batch_output_action_on_conflict: str = "ignore"
    replace_underscore: bool = True
    download_endpoint: str = ""
    replace_underscore_excludes: str = _DEFAULT_UNDERSCORE_EXCLUDES


# Exact field set of TaggerJobRequest; anything else (e.g. confirmationTicketId)
# is dropped before the request is built.
_KNOWN_FIELDS = frozenset(f for f in TaggerJobRequest.__dataclass_fields__)

_NUMBER_FIELDS = {"threshold", "character_threshold"}
_BOOL_FIELDS = {
    "add_rating_tag",
    "add_model_tag",
    "escape_tag",
    "batch_input_recursive",
    "replace_underscore",
}
_STRING_FIELDS = {
    "path",
    "interrogator_model",
    "additional_tags",
    "exclude_tags",
    "batch_output_action_on_conflict",
    "replace_underscore_excludes",
    "download_endpoint",
}


def available_models() -> list[str]:
    """Sorted tagger model keys, for Tool descriptions and validation errors."""
    return sorted(available_interrogators)


def start_tagger_job(params: dict[str, Any]) -> dict[str, Any]:
    """Validate and launch a batch tagging job on a daemon thread.

    Returns the initial progress snapshot.  Raises :class:`TaggerToolError`
    for an unknown model, an already-busy job or invalid parameters.
    """
    model_key = str(params.get("interrogator_model") or _DEFAULT_MODEL)
    if model_key not in available_interrogators:
        raise TaggerToolError(
            "TAGGER_MODEL_UNKNOWN",
            f"Unknown tagger model '{model_key}'. Available models: {', '.join(available_models())}.",
            status_code=400,
        )
    if tagger_progress.is_busy():
        raise TaggerToolError(
            "TAGGER_BUSY",
            "A tagging or download job is already running. Cancel it or wait for it to finish before starting another.",
            status_code=409,
        )

    clean = {key: value for key, value in params.items() if key in _KNOWN_FIELDS}
    clean.setdefault("path", "")
    req = _build_request(clean)

    thread = threading.Thread(target=run_interrogate_job, args=(req,), daemon=True, name="agent-tagger-job")
    thread.start()
    return {
        "state": "started",
        "model": model_key,
        "path": req.path,
        "snapshot": _snapshot(),
    }


def tagger_status() -> dict[str, Any]:
    """Return the current job state plus the live progress snapshot."""
    return {
        "state": "busy" if tagger_progress.is_busy() else "idle",
        "snapshot": _snapshot(),
    }


def cancel_tagger_job() -> dict[str, Any]:
    """Request a cooperative cancel. Idempotent: cancelling when idle is a no-op."""
    cancelled = tagger_progress.request_cancel()
    return {
        "state": "cancelling" if cancelled else "idle",
        "cancelled": cancelled,
        "snapshot": _snapshot(),
    }


def _build_request(clean: dict[str, Any]) -> TaggerJobRequest:
    for key in _NUMBER_FIELDS:
        if key not in clean:
            continue
        value = clean[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TaggerToolError("TAGGER_PARAMS_INVALID", f"Field '{key}' must be a number.", status_code=400)
        value = float(value)
        if not 0.0 <= value <= 1.0:
            raise TaggerToolError("TAGGER_PARAMS_INVALID", f"Field '{key}' must be between 0 and 1.", status_code=400)
        clean[key] = value
    for key in _BOOL_FIELDS:
        if key in clean and not isinstance(clean[key], bool):
            raise TaggerToolError("TAGGER_PARAMS_INVALID", f"Field '{key}' must be a boolean.", status_code=400)
    for key in _STRING_FIELDS:
        if key in clean and not isinstance(clean[key], str):
            raise TaggerToolError("TAGGER_PARAMS_INVALID", f"Field '{key}' must be a string.", status_code=400)
    req = TaggerJobRequest(**clean)
    if not str(req.path).strip():
        raise TaggerToolError("TAGGER_PARAMS_INVALID", "A non-empty image path or glob is required.", status_code=400)
    return req


def _snapshot() -> dict[str, Any]:
    return dict(tagger_progress.get())

"""Host-side remote vision reviewer for ``dataset_review_images``.

The deterministic audit module (``audit.py``) deliberately contains no model
implementation: image-capable review requires a *remote* model call.  This
module provides the host's approved remote reviewer: an OpenAI-compatible
chat-completions endpoint (by default the pinned Qwen3.8-27B bridge) that
receives one image plus its paired caption and returns a strict JSON verdict.

Configuration is environment-based so the same host build works everywhere:

* ``MIKAZUKI_VISION_REVIEW_URL``   -- full chat-completions URL
  (default ``http://127.0.0.1:32222/v1/chat/completions``);
* ``MIKAZUKI_VISION_REVIEW_KEY``   -- bearer key; **when empty no reviewer is
  configured** and ``dataset_review_images`` falls back to the agent-reported
  capability path (text-only => ``MODEL_CAPABILITY_UNAVAILABLE``);
* ``MIKAZUKI_VISION_REVIEW_MODEL`` -- model id sent in the request
  (default ``Qwen3.8-27B``).

The reviewer never fabricates findings: any decode/parse failure is raised and
``review_images`` records the item as ``unavailable`` (``REMOTE_REVIEW_FAILED``).
"""
from __future__ import annotations

import base64
import io
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .audit import ActiveModelCapability, InventoryItem
from .errors import DatasetReviewError

ENV_URL = "MIKAZUKI_VISION_REVIEW_URL"
ENV_KEY = "MIKAZUKI_VISION_REVIEW_KEY"
ENV_MODEL = "MIKAZUKI_VISION_REVIEW_MODEL"
DEFAULT_URL = "http://127.0.0.1:32222/v1/chat/completions"
DEFAULT_MODEL = "Qwen3.8-27B"
MAX_SIDE = 1024
_JPEG_QUALITY = 85

_ALLOWED_ISSUES = frozenset({
    "blurry", "overexposed", "underexposed", "occluded", "bad_crop",
    "watermark", "compression_artifact", "low_detail", "incomplete_subject",
    "mixed_subjects", "unusable",
})
_ALLOWED_MATCH = frozenset({"ok", "partial", "mismatch"})
_ALLOWED_SEVERITY = frozenset({"ok", "minor", "major"})

_REVIEW_PROMPT = (
    "You are auditing one image from an AI character-training dataset.\n\n"
    "Paired caption (sidecar file):\n\"\"\"\n{caption}\n\"\"\"\n\n"
    "Look ONLY at the image and judge it for training quality:\n"
    '- caption_match: "ok" | "partial" | "mismatch" -- does the image depict the captioned subject?\n'
    '- visual_issues: array, subset of '
    '["blurry","overexposed","underexposed","occluded","bad_crop","watermark",'
    '"compression_artifact","low_detail","incomplete_subject","mixed_subjects","unusable"]\n'
    '- identity_notes: one short sentence on subject/identity consistency for character LoRA training, or null\n'
    '- caption_suggestion: a concrete caption correction or completion, or null\n'
    '- severity: "ok" | "minor" | "major"\n\n'
    "Output ONLY minified JSON with exactly these keys, no markdown, no commentary:\n"
    '{{"caption_match":"ok","visual_issues":[],"identity_notes":null,"caption_suggestion":null,"severity":"ok"}}'
)


def _encode_image_jpeg(path: Path) -> str:
    """Return a base64 JPEG data-url payload for the image, bounded to MAX_SIDE."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow ships with the host venv
        raise DatasetReviewError("IMAGE_DECODER_UNAVAILABLE", "Pillow is required for image review.", status_code=500) from None
    if not path.is_file():
        raise DatasetReviewError("DATASET_FILE_MISSING", "Review image is missing.", status_code=404)
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            if max(image.width, image.height) > MAX_SIDE:
                image.thumbnail((MAX_SIDE, MAX_SIDE))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except DatasetReviewError:
        raise
    except Exception as exc:
        raise DatasetReviewError("IMAGE_DECODE_FAILED", "Review image could not be decoded.", details={"reason": type(exc).__name__}, status_code=422) from None


def _extract_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object out of a model answer (fences tolerated)."""
    if not isinstance(text, str):
        raise ValueError("model answer is not text")
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model answer")
    parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model answer is not a JSON object")
    return parsed


def _normalize_findings(raw: dict[str, Any], caption: str | None) -> dict[str, Any]:
    match = str(raw.get("caption_match") or raw.get("captionMatch") or "").lower()
    if match not in _ALLOWED_MATCH:
        raise ValueError("invalid caption_match")
    issues_raw = raw.get("visual_issues", raw.get("visualIssues") or [])
    if not isinstance(issues_raw, list):
        raise ValueError("visual_issues is not a list")
    issues = tuple(sorted({str(issue).lower() for issue in issues_raw if str(issue).lower() in _ALLOWED_ISSUES}))
    identity = raw.get("identity_notes", raw.get("identityNotes"))
    caption_suggestion = raw.get("caption_suggestion", raw.get("captionSuggestion"))
    severity = str(raw.get("severity") or "").lower()
    if severity not in _ALLOWED_SEVERITY:
        raise ValueError("invalid severity")
    return {
        "captionMatch": match,
        "visualIssues": list(issues),
        "identityNotes": str(identity) if identity is not None else None,
        "captionSuggestion": str(caption_suggestion) if caption_suggestion is not None else None,
        "severity": severity,
        "captionUnderReview": caption,
    }


Transport = Callable[[str, str, str, dict[str, Any]], tuple[int, dict[str, Any]]]


@dataclass(frozen=True)
class BridgeVisionReviewer:
    """One approved remote reviewer: an OpenAI-compatible vision endpoint.

    Implements the ``RemoteReviewer`` protocol: ``reviewer(item, capability)``.
    A bound reviewer (see :meth:`with_root`) resolves each inventory item's
    ``relative_path`` against the dataset root to locate the image file.
    """

    url: str
    api_key: str
    model: str
    timeout: float = 240.0
    transport: Transport | None = None
    sleep: Callable[[float], None] = time.sleep
    root: Path | None = None

    @property
    def capability(self) -> ActiveModelCapability:
        return ActiveModelCapability(model=self.model, vision=True, capabilities=("text", "image"))

    def with_root(self, root: str | Path) -> "BridgeVisionReviewer":
        from dataclasses import replace

        return replace(self, root=Path(root))

    def __call__(self, item: InventoryItem, capability: ActiveModelCapability) -> Mapping[str, Any]:
        if self.root is None:
            raise DatasetReviewError("REVIEW_ROOT_REQUIRED", "Reviewer must be bound to a dataset root via with_root().", status_code=500)
        return self.review_file(self.root / item.relative_path, item, capability)

    def review_file(self, path: Path, item: InventoryItem, capability: ActiveModelCapability | None = None) -> Mapping[str, Any]:
        """Review one inventory image; returns normalized findings (strict JSON)."""
        payload_b64 = _encode_image_jpeg(path)
        caption = item.caption_text if item.caption_text is not None else "(no caption file found)"
        body = {
            "model": self.model,
            "max_tokens": 2000,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _REVIEW_PROMPT.format(caption=caption)},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{payload_b64}"}},
                    ],
                }
            ],
        }
        status, payload = self._post_with_retry(body)
        try:
            content = payload["choices"][0]["message"]["content"]
        except (TypeError, KeyError, IndexError) as exc:
            raise ValueError("model response shape is invalid") from exc
        return _normalize_findings(_extract_json_object(content), item.caption_text)

    _RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

    def _post_with_retry(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                if self.transport is not None:
                    status, payload = self.transport(self.url, self.api_key, self.model, body)
                    if 200 <= int(status) < 300:
                        return int(status), payload
                    if int(status) in self._RETRYABLE_STATUS and attempt == 0:
                        self.sleep(2.0)
                        continue
                    raise DatasetReviewError("REMOTE_REVIEW_HTTP", "Vision review endpoint rejected the request.", details={"status": int(status)}, status_code=502)
                request = Request(
                    self.url,
                    data=json.dumps(body).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    method="POST",
                )
                with urlopen(request, timeout=self.timeout) as response:  # nosec B310 - operator-configured URL
                    return int(response.status), json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt == 0:
                    last_error = exc
                    self.sleep(2.0)
                    continue
                raise DatasetReviewError("REMOTE_REVIEW_HTTP", "Vision review endpoint rejected the request.", details={"status": exc.code}, status_code=502) from None
            except (URLError, TimeoutError, OSError) as exc:
                if attempt == 0:
                    last_error = exc
                    self.sleep(2.0)
                    continue
                raise DatasetReviewError("REMOTE_REVIEW_UNREACHABLE", "Vision review endpoint is unreachable.", details={"reason": type(exc).__name__}, status_code=502) from None
            except ValueError as exc:
                raise DatasetReviewError("REMOTE_REVIEW_BAD_RESPONSE", "Vision review endpoint returned an invalid payload.", details={"reason": str(exc)}, status_code=502) from None
        raise DatasetReviewError("REMOTE_REVIEW_UNREACHABLE", "Vision review endpoint is unreachable.", details={"reason": type(last_error).__name__ if last_error else "unknown"}, status_code=502)


def get_configured_reviewer() -> BridgeVisionReviewer | None:
    """Return the configured remote reviewer, or ``None`` when unconfigured."""
    key = os.environ.get(ENV_KEY, "").strip()
    if not key:
        return None
    url = os.environ.get(ENV_URL, "").strip() or DEFAULT_URL
    model = os.environ.get(ENV_MODEL, "").strip() or DEFAULT_MODEL
    return BridgeVisionReviewer(url=url, api_key=key, model=model)


__all__ = [
    "BridgeVisionReviewer",
    "DEFAULT_MODEL",
    "DEFAULT_URL",
    "ENV_KEY",
    "ENV_MODEL",
    "ENV_URL",
    "get_configured_reviewer",
]

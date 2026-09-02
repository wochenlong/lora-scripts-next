"""Optional external renderer for ``artifact_compare``.

``compare_artifacts`` accepts an injected ``renderer`` callable; without one it
reports every cell as ``renderer_unavailable`` instead of fabricating images.
This module provides the host's pluggable renderer: an HTTP generation service
operated by the user (for example a small bridge in front of ComfyUI) that
receives one fixed-protocol render request and returns the produced image.

The renderer never touches the local filesystem and never downloads models.
It posts the *logical* artifact identity (the record already strips arbitrary
filesystem paths) plus the fixed prompt/seed/generation config; mapping the
artifact (e.g. ``contentHash``) to an actual checkpoint file is the service's
responsibility.

Configuration is environment-based:

* ``MIKAZUKI_ARTIFACT_RENDERER_URL``   -- full render endpoint URL; **when empty
  no renderer is configured** and ``artifact_compare`` keeps reporting
  ``renderer_unavailable``;
* ``MIKAZUKI_ARTIFACT_RENDERER_KEY``   -- optional bearer key;
* ``MIKAZUKI_ARTIFACT_RENDERER_BASE_MODEL`` -- optional base-model id included
  in every request.

Request body::

    {"artifact": {...logical record...}, "prompt": str, "seed": int,
     "generationConfig": {...}, "baseModel": str | null}

Expected response body::

    {"state": "success" | "failed", "failure": str?, "imageId": str?,
     "imageB64": str?, "contentHash": str?, "metadata": {...}?,
     "sizeBytes": int?}
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .artifacts import ArtifactRecord

ENV_URL = "MIKAZUKI_ARTIFACT_RENDERER_URL"
ENV_KEY = "MIKAZUKI_ARTIFACT_RENDERER_KEY"
ENV_BASE_MODEL = "MIKAZUKI_ARTIFACT_RENDERER_BASE_MODEL"


@dataclass(frozen=True)
class HttpArtifactRenderer:
    """Render one (artifact, prompt) pair through an external HTTP service."""

    url: str
    api_key: str = ""
    base_model: str = ""
    timeout: float = 3600.0
    # test seam: (url, headers, body) -> (status, payload)
    transport: Callable[[str, dict[str, str], str], tuple[int, dict[str, Any]]] | None = None

    def __call__(
        self,
        record: ArtifactRecord | Mapping[str, Any],
        prompt: str,
        seed: int,
        generation_config: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        record = record if isinstance(record, ArtifactRecord) else ArtifactRecord.from_mapping(dict(record))
        body = {
            "artifact": record.as_dict(),
            "prompt": prompt,
            "seed": int(seed),
            "generationConfig": dict(generation_config),
            "baseModel": self.base_model or None,
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload_bytes = json.dumps(body).encode("utf-8")
        if self.transport is not None:
            status, payload = self.transport(self.url, headers, payload_bytes.decode("utf-8"))
        else:
            request = Request(self.url, data=payload_bytes, headers=headers, method="POST")
            try:
                with urlopen(request, timeout=self.timeout) as response:  # nosec B310 - operator-configured URL
                    status = int(response.status)
                    payload = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                return {"state": "failed", "failure": f"renderer_http_{exc.code}"}
            except (URLError, TimeoutError, OSError) as exc:
                return {"state": "failed", "failure": f"renderer_unreachable:{type(exc).__name__}"}
            except ValueError:
                return {"state": "failed", "failure": "renderer_invalid_response"}
        if not (200 <= int(status) < 300) or not isinstance(payload, dict):
            return {"state": "failed", "failure": "renderer_invalid_response"}
        result: dict[str, Any] = {
            "state": "success" if str(payload.get("state", "success")).lower() == "success" else "failed",
        }
        if result["state"] != "success":
            result["failure"] = str(payload.get("failure") or "renderer_failed")
        for key in ("imageId", "imageB64", "contentHash", "sizeBytes"):
            if payload.get(key) is not None:
                result[key] = payload[key]
        metadata = payload.get("metadata")
        if isinstance(metadata, Mapping):
            result["metadata"] = dict(metadata)
        return result


def get_configured_renderer() -> HttpArtifactRenderer | None:
    """Return the configured renderer, or ``None`` when unconfigured."""
    url = os.environ.get(ENV_URL, "").strip()
    if not url:
        return None
    key = os.environ.get(ENV_KEY, "").strip()
    base_model = os.environ.get(ENV_BASE_MODEL, "").strip()
    return HttpArtifactRenderer(url=url, api_key=key, base_model=base_model)


__all__ = ["ENV_BASE_MODEL", "ENV_KEY", "ENV_URL", "HttpArtifactRenderer", "get_configured_renderer"]

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .errors import AgentSkillError, ErrorCode
from .models import CivitaiEvidenceRecord, Confidence, EvidenceType


API_ROOT = "https://civitai.com/api/v1"
_ALLOWED_SORT = {"Most Downloaded", "Highest Rated", "Newest"}
_ALLOWED_PERIOD = {"AllTime", "Year", "Month", "Week"}
_PARAMETER_KEYS = {
    "rank", "dim", "alpha", "learning_rate", "unet_lr", "text_encoder_lr",
    "optimizer", "scheduler", "epochs", "steps", "batch_size",
    "gradient_accumulation", "resolution", "buckets", "repeats", "image_count",
    "network_type", "conv_dim", "dropout", "precision", "cache_latents",
    "gradient_checkpointing", "caption_strategy", "base_model", "vae", "clip_skip",
}
_KEY_ALIASES = {
    "learningRate": "learning_rate", "learning_rate": "learning_rate",
    "unetLR": "unet_lr", "unet_lr": "unet_lr", "textEncoderLR": "text_encoder_lr",
    "text_encoder_lr": "text_encoder_lr", "batchSize": "batch_size",
    "gradientAccumulation": "gradient_accumulation", "gradient_accumulation_steps": "gradient_accumulation",
    "imageCount": "image_count", "networkType": "network_type", "convDim": "conv_dim",
    "cacheLatents": "cache_latents", "gradientCheckpointing": "gradient_checkpointing",
    "captionStrategy": "caption_strategy", "baseModel": "base_model",
}


@dataclass(frozen=True)
class CivitaiQuery:
    base_model: str | None = None
    sort: str = "Most Downloaded"
    period: str = "AllTime"
    nsfw: bool = False
    limit: int = 20
    cursor: str | None = None

    def validate(self) -> None:
        if self.sort not in _ALLOWED_SORT or self.period not in _ALLOWED_PERIOD:
            raise AgentSkillError(ErrorCode.INVALID_QUERY, "unsupported Civitai sort or period")
        if not isinstance(self.limit, int) or isinstance(self.limit, bool) or not 1 <= self.limit <= 100:
            raise AgentSkillError(ErrorCode.INVALID_QUERY, "Civitai limit must be between 1 and 100")
        if self.nsfw is not False:
            raise AgentSkillError(ErrorCode.INVALID_QUERY, "NSFW discovery is disabled")
        if self.cursor is not None and (not isinstance(self.cursor, str) or len(self.cursor) > 512):
            raise AgentSkillError(ErrorCode.INVALID_QUERY, "Civitai cursor is invalid")


class CivitaiClient:
    """Anonymous, official Civitai API client with bounded serial retries.

    ``transport`` is an optional test seam accepting ``(method, url, params)``
    and returning ``(status, payload, headers)``.  The production path uses
    urllib and sends no credential or model/image download request.
    """

    def __init__(
        self,
        *,
        base_url: str = API_ROOT,
        transport: Callable[[str, str, dict[str, Any]], Any] | None = None,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not _is_official_base(base_url):
            raise AgentSkillError(ErrorCode.OFFICIAL_SOURCE_REQUIRED, "Civitai client requires the official API host")
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.max_retries = max(0, min(int(max_retries), 3))
        self.sleep = sleep

    def search_loras(self, query: CivitaiQuery | None = None) -> dict[str, Any]:
        query = query or CivitaiQuery()
        query.validate()
        params: dict[str, Any] = {
            "types": "LORA", "sort": query.sort, "period": query.period,
            "nsfw": "false", "limit": query.limit,
        }
        if query.base_model:
            params["baseModels"] = query.base_model
        if query.cursor:
            params["cursor"] = query.cursor
        payload = self._get("/models", params)
        items = payload.get("items", []) if isinstance(payload, dict) else []
        if not isinstance(items, list):
            raise AgentSkillError(ErrorCode.RESPONSE_INVALID, "Civitai response items are invalid")
        records = [normalize_lora_record(item, retrieved_at=_now()) for item in items]
        # Public API may return a cursor under metadata or at the top level.
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        next_cursor = metadata.get("nextCursor") if isinstance(metadata, dict) else None
        return {"records": records, "next_cursor": next_cursor, "query": params}

    def get_version(self, version_id: int | str) -> CivitaiEvidenceRecord:
        try:
            parsed_id = int(version_id)
        except (TypeError, ValueError):
            raise AgentSkillError(ErrorCode.INVALID_QUERY, "Civitai version id is invalid")
        if parsed_id <= 0:
            raise AgentSkillError(ErrorCode.INVALID_QUERY, "Civitai version id is invalid")
        payload = self._get(f"/model-versions/{parsed_id}", {})
        return normalize_lora_record(payload, retrieved_at=_now(), version_only=True)

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        for attempt in range(self.max_retries + 1):
            try:
                if self.transport:
                    result = self.transport("GET", url, dict(params))
                    status, payload, headers = _unpack_transport_result(result)
                else:
                    query = urlencode({key: str(value).lower() if isinstance(value, bool) else value for key, value in params.items()})
                    request = Request(f"{url}?{query}" if query else url, headers={"Accept": "application/json"}, method="GET")
                    with urlopen(request, timeout=20) as response:  # nosec B310 - fixed official host
                        status = int(response.status)
                        headers = dict(response.headers.items())
                        payload = json.loads(response.read().decode("utf-8"))
                if status == 429:
                    retry_after = _retry_after(headers)
                    if attempt < self.max_retries:
                        self.sleep(retry_after if retry_after is not None else min(2**attempt, 8))
                        continue
                    raise AgentSkillError(ErrorCode.RATE_LIMITED, "Civitai API rate limit reached", retry_after=retry_after)
                if status < 200 or status >= 300:
                    raise AgentSkillError(ErrorCode.NETWORK_ERROR, f"Civitai API returned HTTP {status}")
                if not isinstance(payload, dict):
                    raise AgentSkillError(ErrorCode.RESPONSE_INVALID, "Civitai API response is not an object")
                return payload
            except AgentSkillError:
                raise
            except Exception as exc:
                if attempt < self.max_retries:
                    self.sleep(min(2**attempt, 8))
                    continue
                raise AgentSkillError(ErrorCode.NETWORK_ERROR, "Civitai API request failed") from exc
        raise AgentSkillError(ErrorCode.NETWORK_ERROR, "Civitai API request failed")


def normalize_lora_record(
    payload: dict[str, Any],
    *,
    retrieved_at: str | None = None,
    version_only: bool = False,
) -> CivitaiEvidenceRecord:
    """Map only explicit API/creator fields; never infer undisclosed training data."""
    if not isinstance(payload, dict):
        raise AgentSkillError(ErrorCode.INVALID_RECORD, "Civitai record must be an object")
    model = payload.get("model") if isinstance(payload.get("model"), dict) else payload
    version = payload.get("modelVersion") if isinstance(payload.get("modelVersion"), dict) else payload
    if version is payload and isinstance(payload.get("modelVersions"), list) and payload["modelVersions"]:
        candidate = payload["modelVersions"][0]
        if isinstance(candidate, dict):
            version = candidate
    model_type = str(model.get("type") or "LORA").upper()
    nsfw = bool(model.get("nsfw") or payload.get("nsfw"))
    model_id = _int_or_none(model.get("id"))
    version_id = _int_or_none(version.get("id"))
    source_url = _source_url(model_id, version_id, version_only)
    creator_obj = model.get("creator")
    creator = creator_obj.get("username") if isinstance(creator_obj, dict) else _str_or_none(model.get("creator"))
    base_model = _str_or_none(version.get("baseModel") or model.get("baseModel"))
    training_details = version.get("trainingDetails")
    if not isinstance(training_details, dict):
        training_details = None
    params = _explicit_parameters(training_details)
    missing = sorted(key for key, value in params.items() if value == "unknown")
    evidence_types = [EvidenceType.API_METADATA]
    if training_details:
        evidence_types.append(EvidenceType.CREATOR_DECLARED)
    if not training_details:
        evidence_types.append(EvidenceType.UNKNOWN)
    stats = model.get("stats") if isinstance(model.get("stats"), dict) else {}
    trained_words = version.get("trainedWords") if isinstance(version.get("trainedWords"), list) else []
    record = CivitaiEvidenceRecord(
        source_url=source_url,
        model_id=model_id,
        model_version_id=version_id,
        retrieved_at=retrieved_at or _now(),
        creator=creator,
        base_model=base_model,
        lora_category=_category(model, version),
        published_at=_str_or_none(model.get("publishedAt") or version.get("createdAt")),
        stats={key: value for key, value in stats.items() if key in {"downloadCount", "ratingCount", "rating", "favoriteCount"}},
        trained_words=[str(word) for word in trained_words if isinstance(word, (str, int, float))],
        training_details=training_details,
        disclosed_dataset_summary=_str_or_none(training_details.get("dataset") if training_details else None),
        preview_metadata_summary=None,
        permissions={"nsfw": nsfw, "public": True},
        evidence_types=evidence_types,
        missing_fields=missing,
        normalized_parameters=params,
        confidence=Confidence.MEDIUM if training_details else Confidence.LOW,
        excluded=model_type != "LORA" or nsfw,
        exclusion_reason=("not_lora" if model_type != "LORA" else "nsfw" if nsfw else None),
    )
    return record


def _explicit_parameters(details: dict[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {key: "unknown" for key in sorted(_PARAMETER_KEYS)}
    result: dict[str, Any] = {}
    for key, value in details.items():
        normalized = _KEY_ALIASES.get(key, key)
        if normalized in _PARAMETER_KEYS and value is not None and value != "":
            result[normalized] = value
    return {key: result.get(key, "unknown") for key in sorted(_PARAMETER_KEYS)}


def _category(model: dict[str, Any], version: dict[str, Any]) -> str:
    value = model.get("loraCategory") or version.get("loraCategory")
    if value in {"character", "style", "clothing", "concept", "utility"}:
        return value
    # Tags are only a declared category hint when the API explicitly labels one.
    return "unknown"


def _source_url(model_id: int | None, version_id: int | None, version_only: bool) -> str:
    if version_only and version_id:
        return f"{API_ROOT}/model-versions/{version_id}"
    if model_id:
        return f"{API_ROOT}/models/{model_id}"
    if version_id:
        return f"{API_ROOT}/model-versions/{version_id}"
    return f"{API_ROOT}/models/unknown"


def _is_official_base(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.netloc.lower() in {"civitai.com", "www.civitai.com"} and parsed.path.rstrip("/") in {"/api/v1", ""}


def _unpack_transport_result(result: Any) -> tuple[int, dict[str, Any], dict[str, Any]]:
    if isinstance(result, tuple) and len(result) == 3:
        status, payload, headers = result
        return int(status), payload, headers or {}
    status = int(getattr(result, "status_code", getattr(result, "status", 200)))
    payload = result.json() if callable(getattr(result, "json", None)) else getattr(result, "payload", {})
    headers = dict(getattr(result, "headers", {}) or {})
    return status, payload, headers


def _retry_after(headers: dict[str, Any]) -> float | None:
    value = headers.get("Retry-After") or headers.get("retry-after")
    try:
        return max(0.0, min(float(value), 60.0)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    return str(value) if value is not None and str(value).strip() else None


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = ["API_ROOT", "CivitaiClient", "CivitaiQuery", "normalize_lora_record"]

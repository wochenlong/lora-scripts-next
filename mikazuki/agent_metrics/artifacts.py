from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence


DEFAULT_WEIGHTS: dict[str, float] = {
    "quality": 0.40,
    "overfitRisk": 0.25,
    "stability": 0.20,
    "efficiency": 0.15,
}
_PATH_METADATA_KEY = re.compile(r"(?:^|_)(?:path|filepath|filename|directory|dirname|root)(?:$|_)", re.I)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_metadata(value: Any, key: str = "") -> Any:
    """Keep descriptive metadata while dropping arbitrary filesystem paths."""
    if key and _PATH_METADATA_KEY.search(key):
        return None
    if isinstance(value, Mapping):
        return {str(child_key): child_value for child_key, child in value.items() if (child_value := _safe_metadata(child, str(child_key))) is not None}
    if isinstance(value, (list, tuple)):
        return [_safe_metadata(child, key) for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass(frozen=True)
class ArtifactRecord:
    """Logical artifact metadata; arbitrary filesystem paths are excluded."""

    artifact_id: str
    step: int | float | None = None
    epoch: int | float | None = None
    content_hash: str | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)
    available_prompts: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ArtifactRecord":
        artifact_id = value.get("artifactId", value.get("artifact_id", value.get("id")))
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise ValueError("artifact_id is required")
        prompts = value.get("availablePrompts", value.get("available_prompts", ())) or ()
        if isinstance(prompts, str):
            prompts = (prompts,)
        return cls(
            artifact_id=artifact_id,
            step=value.get("step"), epoch=value.get("epoch"),
            content_hash=value.get("contentHash", value.get("content_hash")),
            metrics=_safe_metadata(dict(value.get("metrics") or {})),
            available_prompts=tuple(str(prompt) for prompt in prompts),
            metadata=_safe_metadata(dict(value.get("metadata") or {})),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id, "step": self.step, "epoch": self.epoch,
            "contentHash": self.content_hash, "metrics": _safe_metadata(dict(self.metrics)),
            "availablePrompts": list(self.available_prompts), "metadata": _safe_metadata(dict(self.metadata)),
        }


@dataclass(frozen=True)
class FixedComparisonProtocol:
    """Immutable comparison conditions shared by every candidate."""

    prompts: tuple[str, ...]
    seed: int
    generation_config: Mapping[str, Any]
    max_artifacts: int = 5
    protocol_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.prompts or len(self.prompts) > 4:
            raise ValueError("fixed protocol requires 1 to 4 prompts")
        if any(not isinstance(prompt, str) or not prompt.strip() for prompt in self.prompts):
            raise ValueError("prompts must be non-empty strings")
        if len(set(self.prompts)) != len(self.prompts):
            raise ValueError("prompts must be unique")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("seed must be an integer")
        if self.max_artifacts < 1 or self.max_artifacts > 5:
            raise ValueError("max_artifacts must be between 1 and 5")
        if not isinstance(self.generation_config, Mapping):
            raise ValueError("generation_config must be an object")

    @property
    def protocol_id(self) -> str:
        return _hash({"version": self.protocol_version, "prompts": list(self.prompts), "seed": self.seed, "generationConfig": dict(self.generation_config)})

    def as_dict(self) -> dict[str, Any]:
        return {"protocolId": self.protocol_id, "protocolVersion": self.protocol_version, "prompts": list(self.prompts), "seed": self.seed, "generationConfig": dict(self.generation_config), "maxArtifacts": self.max_artifacts}


@dataclass(frozen=True)
class ArtifactComparison:
    protocol: dict[str, Any]
    candidates: list[dict[str, Any]]
    coverage: float
    confidence: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Recommendation:
    artifact_id: str
    rank: int
    score: float | None
    components: Mapping[str, float | None]
    weights: Mapping[str, float]
    coverage: float
    confidence: str
    missing_dimensions: tuple[str, ...]
    strengths: tuple[str, ...]
    caveats: tuple[str, ...]
    evidence: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"artifactId": self.artifact_id, "rank": self.rank, "score": self.score, "components": dict(self.components), "weights": dict(self.weights), "coverage": self.coverage, "confidence": self.confidence, "missingDimensions": list(self.missing_dimensions), "strengths": list(self.strengths), "caveats": list(self.caveats), "evidence": dict(self.evidence)}


def _record(value: ArtifactRecord | Mapping[str, Any]) -> ArtifactRecord:
    return value if isinstance(value, ArtifactRecord) else ArtifactRecord.from_mapping(value)


def compare_artifacts(
    artifacts: Iterable[ArtifactRecord | Mapping[str, Any]],
    protocol: FixedComparisonProtocol,
    *,
    renderer: Callable[[ArtifactRecord, str, int, Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
) -> ArtifactComparison:
    """Compare up to five artifacts under exactly one fixed protocol.

    ``renderer`` is injected by the Host and may return an image logical ID,
    hash and metadata.  A failure is retained in the DTO rather than removed.
    """
    records = sorted((_record(item) for item in artifacts), key=lambda item: item.artifact_id)
    if len(records) > protocol.max_artifacts:
        raise ValueError(f"at most {protocol.max_artifacts} artifacts are allowed")
    if len({record.artifact_id for record in records}) != len(records):
        raise ValueError("artifact IDs must be unique")
    candidates: list[dict[str, Any]] = []
    total = len(records) * len(protocol.prompts)
    successes = 0
    for record in records:
        results: list[dict[str, Any]] = []
        for prompt in protocol.prompts:
            item = {"prompt": prompt, "seed": protocol.seed, "generationConfig": dict(protocol.generation_config), "state": "failed", "failure": "renderer_unavailable"}
            if renderer is not None:
                try:
                    rendered = renderer(record, prompt, protocol.seed, protocol.generation_config)
                    if rendered is not None:
                        rendered_data = dict(rendered)
                        rendered_state = str(rendered_data.get("state", "success"))
                        item.update(rendered_data)
                        item["state"] = "success" if rendered_state == "success" else rendered_state
                        if item["state"] == "success":
                            successes += 1
                        elif not item.get("failure"):
                            item["failure"] = "renderer_failed"
                except Exception as exc:  # renderer is an external boundary; expose a safe class only
                    item["failure"] = type(exc).__name__
            results.append(item)
        candidates.append({"artifactId": record.artifact_id, "step": record.step, "epoch": record.epoch, "contentHash": record.content_hash, "results": results, "metrics": dict(record.metrics), "available": sum(result["state"] == "success" for result in results), "failed": sum(result["state"] != "success" for result in results)})
    coverage = successes / total if total else 0.0
    confidence = "high" if coverage == 1.0 and total else "medium" if coverage >= 0.5 else "low" if total else "unknown"
    return ArtifactComparison(protocol=protocol.as_dict(), candidates=candidates, coverage=coverage, confidence=confidence)


def list_artifacts(artifacts: Iterable[ArtifactRecord | Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Tool-shaped logical catalog; never returns a filesystem path."""
    records = sorted((_record(item) for item in artifacts), key=lambda item: item.artifact_id)
    if len({record.artifact_id for record in records}) != len(records):
        raise ValueError("artifact IDs must be unique")
    return [record.as_dict() for record in records]


def get_comparison_set(
    artifacts: Iterable[ArtifactRecord | Mapping[str, Any]],
    protocol: FixedComparisonProtocol | Mapping[str, Any], *,
    renderer: Callable[[ArtifactRecord, str, int, Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Accept the JSON contract shape and return a JSON-ready comparison."""
    if not isinstance(protocol, FixedComparisonProtocol):
        protocol = FixedComparisonProtocol(
            prompts=tuple(protocol.get("prompts") or ()), seed=protocol.get("seed"),
            generation_config=protocol.get("generationConfig", protocol.get("generation_config", {})),
            max_artifacts=int(protocol.get("maxArtifacts", protocol.get("max_artifacts", 5))),
            protocol_version=str(protocol.get("protocolVersion", protocol.get("protocol_version", "v1"))),
        )
    return compare_artifacts(artifacts, protocol, renderer=renderer).as_dict()


def _normalise_weights(weights: Mapping[str, Any] | None) -> dict[str, float]:
    result = dict(DEFAULT_WEIGHTS)
    if weights:
        aliases = {"overfit_risk": "overfitRisk", "overfit": "overfitRisk"}
        for key, value in weights.items():
            canonical = aliases.get(str(key), str(key))
            if canonical in result:
                parsed = _float(value)
                if parsed is None or parsed < 0:
                    raise ValueError("weights must be finite non-negative numbers")
                result[canonical] = parsed
    total = sum(result.values())
    if total <= 0:
        raise ValueError("weights must contain a positive total")
    return {key: value / total for key, value in result.items()}


def _component(metrics: Mapping[str, Any], name: str) -> float | None:
    aliases = {
        "quality": ("quality", "qualityScore", "quality_score", "qualityEvidence", "imageQuality", "validationQuality"),
        "overfitRisk": ("overfitRisk", "overfit_risk", "overfit", "overfitScore", "overfitRiskScore"),
        "stability": ("stability", "stabilityScore", "stability_score"),
        "efficiency": ("efficiency", "efficiencyScore", "efficiency_score"),
    }
    for key in aliases[name]:
        value = _float(metrics.get(key))
        if value is not None:
            # Accept either a 0..1 rubric or a 0..100 rubric.  overfitRisk is
            # expressed as desirability: a lower measured risk is better.
            scaled = value * 100.0 if 0.0 <= value <= 1.0 else value
            return max(0.0, min(100.0, 100.0 - scaled if name == "overfitRisk" else scaled))
    return None


def recommend_artifacts(
    artifacts: Iterable[ArtifactRecord | Mapping[str, Any]], *, top_k: int = 3,
    weights: Mapping[str, Any] | None = None, comparison: ArtifactComparison | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rank candidates by weighted evidence with explicit missing dimensions.

    Missing values are omitted from the denominator.  The returned coverage and
    confidence make the reduced evidence visible; no candidate is deleted.
    """
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    normalised = _normalise_weights(weights)
    records = sorted((_record(item) for item in artifacts), key=lambda item: item.artifact_id)
    comparison_data = comparison.as_dict() if isinstance(comparison, ArtifactComparison) else dict(comparison or {})
    if comparison_data:
        comparison_candidates = {str(item.get("artifactId")): item for item in comparison_data.get("candidates", [])}
    else:
        comparison_candidates = {}
    ranked: list[tuple[float, ArtifactRecord, dict[str, float | None], tuple[str, ...], float]] = []
    for record in records:
        components = {name: _component(record.metrics, name) for name in normalised}
        missing = tuple(name for name, value in components.items() if value is None)
        available = [name for name, value in components.items() if value is not None]
        denominator = sum(normalised[name] for name in available)
        score = sum(normalised[name] * float(components[name]) for name in available) / denominator if denominator else None
        coverage = denominator / sum(normalised.values()) if normalised else 0.0
        ranked.append((score if score is not None else -1.0, record, components, missing, coverage))
    ranked.sort(key=lambda item: (-item[0], item[1].artifact_id))
    recommendations: list[dict[str, Any]] = []
    for index, (score, record, components, missing, coverage) in enumerate(ranked[:top_k], start=1):
        caveats = [f"missing dimension: {name}" for name in missing]
        if record.artifact_id in comparison_candidates and comparison_candidates[record.artifact_id].get("failed", 0):
            caveats.append("fixed comparison contains failed prompts")
        confidence = "high" if coverage >= 0.95 and not caveats else "medium" if coverage >= 0.7 else "low" if score >= 0 else "unknown"
        strengths = tuple(name for name, value in components.items() if value is not None and value >= 75)
        evidence = {"metrics": dict(record.metrics), "comparison": comparison_candidates.get(record.artifact_id), "userDecisionRequired": True}
        recommendations.append(Recommendation(record.artifact_id, index, None if score < 0 else round(score, 6), components, normalised, coverage, confidence, missing, strengths, tuple(caveats), evidence).as_dict())
    return {"state": "ranked" if recommendations else "unknown", "weights": normalised, "topK": recommendations, "candidateCount": len(records), "unrankedCount": max(0, len(records) - len(recommendations)), "deletionSupported": False, "userDecisionRequired": True}


# Names used by earlier POC adapters; retain aliases while the Host migrates.
rank_artifacts = recommend_artifacts
build_comparison_set = compare_artifacts


__all__ = ["ArtifactRecord", "FixedComparisonProtocol", "ArtifactComparison", "Recommendation", "DEFAULT_WEIGHTS", "list_artifacts", "compare_artifacts", "get_comparison_set", "build_comparison_set", "recommend_artifacts", "rank_artifacts"]

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvidenceType(str, Enum):
    PROJECT_CONTRACT = "project_contract"
    OFFICIAL_DOCUMENTATION = "official_documentation"
    API_METADATA = "api_metadata"
    CREATOR_DECLARED = "creator_declared"
    PLATFORM_STATISTIC = "platform_statistic"
    LOCAL_EXPERIMENT = "local_experiment"
    MODEL_INFERENCE = "model_inference"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    title: str
    url: str
    version: str = "unknown"
    retrieved_at: str = "unknown"
    scope: str = "unknown"
    evidence_type: EvidenceType = EvidenceType.UNKNOWN

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id, "title": self.title, "url": self.url,
            "version": self.version, "retrieved_at": self.retrieved_at,
            "scope": self.scope, "evidence_type": self.evidence_type.value,
        }


@dataclass(frozen=True)
class KnowledgeDocument:
    source: SourceRef
    text: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeResult:
    source_id: str | None
    title: str
    excerpt: str
    evidence_type: EvidenceType
    version: str
    scope: str
    confidence: Confidence
    unknown: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id, "title": self.title, "excerpt": self.excerpt,
            "evidence_type": self.evidence_type.value, "version": self.version,
            "scope": self.scope, "confidence": self.confidence.value,
            "unknown": self.unknown,
        }


@dataclass
class CivitaiEvidenceRecord:
    source_url: str
    model_id: int | None = None
    model_version_id: int | None = None
    retrieved_at: str = "unknown"
    api_version: str = "v1"
    creator: str | None = None
    base_model: str | None = None
    lora_category: str = "unknown"
    published_at: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    trained_words: list[str] = field(default_factory=list)
    training_details: dict[str, Any] | None = None
    disclosed_dataset_summary: str | None = None
    preview_metadata_summary: str | None = None
    permissions: dict[str, Any] = field(default_factory=dict)
    evidence_types: list[EvidenceType] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    normalized_parameters: dict[str, Any] = field(default_factory=dict)
    confidence: Confidence = Confidence.UNKNOWN
    excluded: bool = False
    exclusion_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result = {
            "sourceUrl": self.source_url, "modelId": self.model_id,
            "modelVersionId": self.model_version_id, "retrievedAt": self.retrieved_at,
            "apiVersion": self.api_version, "creator": self.creator,
            "baseModel": self.base_model, "loraCategory": self.lora_category,
            "publishedAt": self.published_at, "stats": self.stats,
            "trainedWords": self.trained_words, "trainingDetails": self.training_details,
            "disclosedDatasetSummary": self.disclosed_dataset_summary,
            "previewMetadataSummary": self.preview_metadata_summary,
            "permissions": self.permissions,
            "evidenceTypes": [x.value for x in self.evidence_types],
            "missingFields": self.missing_fields,
            "normalizedParameters": self.normalized_parameters,
            "confidence": self.confidence.value, "excluded": self.excluded,
        }
        if self.exclusion_reason:
            result["exclusionReason"] = self.exclusion_reason
        return result


@dataclass
class SkillPackage:
    name: str
    version: str
    scope: dict[str, Any]
    sources: list[SourceRef]
    recommendations: list[dict[str, Any]]
    missingness: dict[str, float]
    caveats: list[str]
    validation_status: str = "unvalidated"
    reviewer: str | None = None
    evals: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "version": self.version, "scope": self.scope,
            "sources": [s.as_dict() for s in self.sources],
            "recommendations": self.recommendations, "missingness": self.missingness,
            "caveats": self.caveats, "validationStatus": self.validation_status,
            "reviewer": self.reviewer, "evals": self.evals,
        }


@dataclass(frozen=True)
class SkillValidation:
    valid: bool
    publishable: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

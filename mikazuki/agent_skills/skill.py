from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable
from urllib.parse import urlparse, urlunparse

from .cohort import CohortReport, build_cohort_report
from .errors import AgentSkillError, ErrorCode
from .models import (
    CivitaiEvidenceRecord,
    Confidence,
    EvidenceType,
    SkillPackage,
    SkillValidation,
    SourceRef,
)


def build_parameter_template(
    report: CohortReport,
    *,
    source_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Turn distributions into explicitly scoped, source-cited suggestions."""
    ids = [str(source_id) for source_id in source_ids if str(source_id).strip()]
    recommendations = []
    for field, value_range in sorted(report.recommended_ranges.items()):
        recommendations.append({
            "parameter": field,
            "suggested_range": {
                "p25": value_range["p25"], "median": value_range["median"], "p75": value_range["p75"],
            },
            "coverage": value_range["coverage"],
            "confidence": value_range["confidence"],
            "source_ids": ids,
            "rationale": "Observed disclosed distribution; popularity is not causal evidence.",
        })
    return recommendations


def draft_skill(
    records: Iterable[CivitaiEvidenceRecord] = (),
    *,
    report: CohortReport | None = None,
    name: str = "lora-parameter-template",
    version: str = "0.1.0-draft",
    scope: dict[str, Any] | None = None,
    sources: Iterable[SourceRef] = (),
    local_validation: str = "not_locally_validated",
) -> SkillPackage:
    records = list(records)
    report = report or build_cohort_report(records)
    source_list = list(sources)
    if not source_list:
        source_list = [
            SourceRef(
                source_id=f"civitai:model:{record.model_id or 'unknown'}:version:{record.model_version_id or 'unknown'}",
                title="Civitai official API record",
                url=_safe_url(record.source_url),
                version=record.api_version,
                retrieved_at=record.retrieved_at,
                scope=f"{record.base_model or 'unknown'} / {record.lora_category or 'unknown'}",
                evidence_type=EvidenceType.API_METADATA,
            )
            for record in records
        ]
    if not source_list:
        source_list = [SourceRef(
            source_id="unknown:empty-cache",
            title="No public evidence retrieved",
            url="https://civitai.com/api/v1/models",
            version="unknown",
            retrieved_at="unknown",
            scope="unknown",
            evidence_type=EvidenceType.UNKNOWN,
        )]
    # Deduplicate source IDs while preserving source order.
    unique_sources = list({source.source_id: source for source in source_list}.values())
    source_ids = [source.source_id for source in unique_sources]
    return SkillPackage(
        name=name,
        version=version,
        scope=scope or {"base_models": sorted({record.base_model or "unknown" for record in records}), "lora_categories": sorted({record.lora_category or "unknown" for record in records})},
        sources=unique_sources,
        recommendations=build_parameter_template(report, source_ids=source_ids),
        missingness=report.missingness,
        caveats=sorted(set([
            "Civitai popularity metrics are for discovery and bias analysis only, not causal quality.",
            "Undisclosed trainingDetails remain unknown and are never filled from previews or filenames.",
            "This draft is exploratory until local reproduction and human review are recorded.",
            *report.bias_flags,
        ])),
        validation_status="validated" if local_validation == "validated" else "unvalidated",
    )


def validate_skill(skill: SkillPackage) -> SkillValidation:
    errors: list[str] = []
    warnings: list[str] = []
    if not skill.name or not skill.version:
        errors.append("name_and_version_required")
    if not isinstance(skill.scope, dict) or not skill.scope:
        errors.append("scope_required")
    source_ids = {source.source_id for source in skill.sources}
    if not skill.sources:
        errors.append("source_required")
    for source in skill.sources:
        if not source.source_id or urlparse(source.url).scheme not in {"https", "http"}:
            errors.append("source_metadata_invalid")
        if source.evidence_type in {EvidenceType.MODEL_INFERENCE, EvidenceType.UNKNOWN}:
            warnings.append("weak_or_unknown_source")
    if not skill.recommendations:
        warnings.append("no_quantitative_recommendations")
    for recommendation in skill.recommendations:
        cited = recommendation.get("source_ids")
        if not isinstance(cited, list) or not cited or not set(cited) <= source_ids:
            errors.append("recommendation_missing_source")
        if recommendation.get("confidence") == Confidence.UNKNOWN.value:
            warnings.append("unknown_recommendation_confidence")
        rationale = str(recommendation.get("rationale", "")).casefold()
        if "causal" in rationale and "not causal" not in rationale:
            errors.append("popularity_causal_claim")
    if skill.validation_status not in {"draft", "unvalidated", "validated"}:
        errors.append("validation_status_invalid")
    if skill.validation_status == "validated":
        if not skill.reviewer:
            errors.append("validated_skill_requires_human_reviewer")
        if not any(source.evidence_type == EvidenceType.LOCAL_EXPERIMENT for source in skill.sources):
            errors.append("validated_skill_requires_local_experiment")
    else:
        warnings.append("not_locally_validated")
    return SkillValidation(valid=not errors, publishable=not errors and bool(skill.reviewer) and skill.validation_status == "validated", errors=tuple(sorted(set(errors))), warnings=tuple(sorted(set(warnings))))


def run_skill_eval(skill: SkillPackage, cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Run bounded deterministic contract cases; no LLM is invoked."""
    validation = validate_skill(skill)
    results = []
    for case in cases:
        expected_ids = set(case.get("expected_source_ids", []))
        cited_ids = {source_id for recommendation in skill.recommendations for source_id in recommendation.get("source_ids", [])}
        expect_unknown = bool(case.get("expect_unknown"))
        passed = bool(expected_ids <= cited_ids) and (not expect_unknown or not skill.recommendations)
        results.append({"case_id": case.get("case_id", "unknown"), "passed": passed})
    passed_count = sum(result["passed"] for result in results)
    return {
        "valid": validation.valid,
        "publishable": validation.publishable,
        "total": len(results),
        "passed": passed_count,
        "score": round(passed_count / len(results), 4) if results else 0.0,
        "results": results,
        "errors": list(validation.errors),
        "warnings": list(validation.warnings),
    }


def _safe_url(value: str) -> str:
    parsed = urlparse(value)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


__all__ = ["build_parameter_template", "draft_skill", "validate_skill", "run_skill_eval"]

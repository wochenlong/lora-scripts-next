from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from math import isnan
from statistics import median
from typing import Any, Iterable

from .models import CivitaiEvidenceRecord, Confidence


@dataclass
class CohortReport:
    sample_count: int
    status: str
    query: dict[str, Any]
    field_coverage: dict[str, float]
    missingness: dict[str, float]
    distributions: dict[str, dict[str, float]]
    recommended_ranges: dict[str, dict[str, Any]]
    creator_concentration: dict[str, Any]
    bias_flags: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.UNKNOWN
    cohorts: dict[str, dict[str, Any]] = field(default_factory=dict)
    counterexamples: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sampleCount": self.sample_count, "status": self.status,
            "query": self.query, "fieldCoverage": self.field_coverage,
            "missingness": self.missingness, "distributions": self.distributions,
            "recommendedRanges": self.recommended_ranges,
            "creatorConcentration": self.creator_concentration,
            "biasFlags": self.bias_flags, "confidence": self.confidence.value,
            "cohorts": self.cohorts, "counterexamples": self.counterexamples,
        }


def build_cohort_report(
    records: Iterable[CivitaiEvidenceRecord],
    *,
    query: dict[str, Any] | None = None,
    rankings: Iterable[str] | None = None,
    time_windows: Iterable[str] | None = None,
    min_sample: int = 30,
    min_coverage: float = 0.60,
) -> CohortReport:
    all_records = list(records)
    eligible = [record for record in all_records if not record.excluded]
    n = len(eligible)
    params = sorted({key for record in eligible for key in record.normalized_parameters})
    coverage: dict[str, float] = {}
    missingness: dict[str, float] = {}
    distributions: dict[str, dict[str, float]] = {}
    for key in params:
        values = [record.normalized_parameters.get(key) for record in eligible]
        known = [value for value in values if not _unknown(value)]
        coverage[key] = round(len(known) / n, 4) if n else 0.0
        missingness[key] = round(1.0 - coverage[key], 4) if n else 1.0
        numeric = [_number(value) for value in known]
        numeric = [value for value in numeric if value is not None]
        if numeric:
            distributions[key] = _distribution(numeric)
    ranges: dict[str, dict[str, Any]] = {}
    for key, stats in distributions.items():
        if coverage[key] < min_coverage:
            continue
        ranges[key] = {
            "p25": stats["p25"], "median": stats["median"], "p75": stats["p75"],
            "coverage": coverage[key], "confidence": _range_confidence(n, coverage[key]),
            "source": "publicly disclosed distribution; not causal",
        }
    concentration = _creator_concentration(eligible)
    flags: list[str] = []
    if n < min_sample:
        flags.append("exploratory_sample_below_30")
    if any(value < min_coverage for value in coverage.values()):
        flags.append("parameter_missingness_limits_comparison")
    if concentration["share"] >= 0.5:
        flags.append("creator_concentration_high")
    if rankings and len(set(rankings)) < 2:
        flags.append("single_ranking_exposure_bias")
    if time_windows and len(set(time_windows)) < 2:
        flags.append("single_time_window_age_bias")
    if any("downloadCount" in record.stats for record in eligible):
        flags.extend(["popularity_is_discovery_only", "survivorship_and_exposure_bias_possible"])
    if not any(record.training_details for record in eligible):
        flags.append("training_details_undisclosed")
    groups: dict[str, list[CivitaiEvidenceRecord]] = defaultdict(list)
    for record in eligible:
        group_name = f"{record.base_model or 'unknown'}:{record.lora_category or 'unknown'}"
        groups[group_name].append(record)
    cohort_data = {
        name: _group_summary(group, min_sample=min_sample, min_coverage=min_coverage)
        for name, group in sorted(groups.items())
    }
    confidence = Confidence.HIGH if n >= min_sample and all(v >= min_coverage for v in coverage.values() or [0]) else Confidence.MEDIUM if n else Confidence.UNKNOWN
    if flags and "training_details_undisclosed" in flags:
        confidence = Confidence.LOW if n else Confidence.UNKNOWN
    return CohortReport(
        sample_count=n,
        status="formal" if n >= min_sample else "exploratory",
        query=query or {},
        field_coverage=coverage,
        missingness=missingness,
        distributions=distributions,
        recommended_ranges=ranges,
        creator_concentration=concentration,
        bias_flags=sorted(set(flags)),
        confidence=confidence,
        cohorts=cohort_data,
        counterexamples=_counterexamples(eligible, ranges),
    )


def _group_summary(records: list[CivitaiEvidenceRecord], *, min_sample: int, min_coverage: float) -> dict[str, Any]:
    count = len(records)
    fields = sorted({key for record in records for key in record.normalized_parameters})
    coverage = {
        key: round(sum(not _unknown(record.normalized_parameters.get(key)) for record in records) / count, 4)
        if count else 0.0
        for key in fields
    }
    confidence = Confidence.HIGH if count >= min_sample and all(v >= min_coverage for v in coverage.values() or [0]) else Confidence.MEDIUM if count else Confidence.UNKNOWN
    return {
        "sampleCount": count, "status": "formal" if count >= min_sample else "exploratory",
        "fieldCoverage": coverage, "confidence": confidence.value,
    }


def _creator_concentration(records: list[CivitaiEvidenceRecord]) -> dict[str, Any]:
    creators = Counter(record.creator or "unknown" for record in records)
    total = sum(creators.values())
    top = creators.most_common(1)[0] if creators else ("unknown", 0)
    return {
        "topCreator": top[0], "topCount": top[1],
        "share": round(top[1] / total, 4) if total else 0.0,
        "uniqueCreators": len(creators),
    }


def _distribution(values: list[float]) -> dict[str, float]:
    values = sorted(values)
    return {
        "min": values[0], "p25": _quantile(values, 0.25), "median": _quantile(values, 0.5),
        "p75": _quantile(values, 0.75), "max": values[-1],
    }


def _quantile(values: list[float], q: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    lower, upper = int(position), min(int(position) + 1, len(values) - 1)
    fraction = position - lower
    return round(values[lower] + (values[upper] - values[lower]) * fraction, 8)


def _range_confidence(sample_count: int, coverage: float) -> str:
    if sample_count >= 100 and coverage >= 0.8:
        return Confidence.HIGH.value
    if sample_count >= 30 and coverage >= 0.6:
        return Confidence.MEDIUM.value
    return Confidence.LOW.value


def _unknown(value: Any) -> bool:
    return value is None or value == "unknown" or value == "" or (isinstance(value, float) and isnan(value))


def _number(value: Any) -> float | None:
    if _unknown(value) or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None


def _counterexamples(records: list[CivitaiEvidenceRecord], ranges: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for record in records:
        outside = []
        for key, value_range in ranges.items():
            value = _number(record.normalized_parameters.get(key))
            if value is not None and not value_range["p25"] <= value <= value_range["p75"]:
                outside.append(key)
        if outside:
            result.append({"modelId": record.model_id, "fieldsOutsideIqr": outside, "sourceUrl": record.source_url})
    return result[:20]


__all__ = ["CohortReport", "build_cohort_report"]

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class CurvePoint:
    """A metric sample.  ``value`` may be NaN/Inf so that failures remain visible."""

    step: float
    value: float

    def as_dict(self) -> dict[str, float | None]:
        # JSON has no portable NaN/Infinity representation.  Keep the exact
        # location/count in the summary and serialize invalid point values as
        # null so a Host JSON response remains standards-compliant.
        return {"step": self.step, "value": self.value if math.isfinite(self.value) else None}


@dataclass(frozen=True)
class CurveSummary:
    metric: str
    source: str
    points: list[dict[str, float]]
    sampled_points: list[dict[str, float]]
    first: float | None
    last: float | None
    minimum: float | None
    maximum: float | None
    finite_count: int
    nan_count: int
    inf_count: int
    missing_count: int
    slope: float | None
    moving: list[dict[str, float | None]]
    plateaus: list[dict[str, float | int | str]]
    spikes: list[dict[str, float | int | str]]
    anomalies: list[dict[str, Any]]
    coverage: float
    confidence: str
    unknown: bool = False
    range_start: float | None = None
    range_end: float | None = None

    def as_dict(self) -> dict[str, Any]:
        # Keep this DTO stable for both the Host API and JSON evidence files.
        result = asdict(self)
        result.update({
            "min": self.minimum,
            "max": self.maximum,
            "sourceRange": {"start": self.range_start, "end": self.range_end},
            "nanInf": {"nanCount": self.nan_count, "infCount": self.inf_count},
        })
        return result


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a metric value")
    result = float(value)
    if not math.isfinite(result) and not (math.isnan(result) or math.isinf(result)):
        raise ValueError("invalid metric value")
    return result


def _coerce_point(item: Any) -> CurvePoint:
    if isinstance(item, CurvePoint):
        return item
    if isinstance(item, Mapping):
        step = item.get("step", item.get("x", item.get("epoch")))
        value = item.get("value", item.get("y", item.get("metric")))
        if step is None or value is None:
            raise ValueError("metric points require step and value")
        return CurvePoint(_number(step), _number(value))
    if isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and len(item) >= 2:
        return CurvePoint(_number(item[0]), _number(item[1]))
    raise ValueError("metric point must be a mapping or a two-item sequence")


def normalize_series(series: Iterable[Any]) -> list[CurvePoint]:
    """Coerce and deterministically sort a series by step (stable on duplicates)."""
    points = [_coerce_point(item) for item in series]
    return sorted(points, key=lambda point: point.step)


def downsample_series(points: Iterable[Any], max_points: int = 200) -> list[CurvePoint]:
    """Return evenly distributed samples while preserving first and last points."""
    if not isinstance(max_points, int) or isinstance(max_points, bool) or max_points < 1 or max_points > 200:
        raise ValueError("max_points must be an integer between 1 and 200")
    ordered = normalize_series(points)
    if len(ordered) <= max_points:
        return ordered
    if max_points == 1:
        return [ordered[0]]
    # Integer index selection avoids interpolation and remains deterministic.
    indices = [round(index * (len(ordered) - 1) / (max_points - 1)) for index in range(max_points)]
    return [ordered[index] for index in indices]


def detect_nan_inf(points: Iterable[Any]) -> dict[str, Any]:
    ordered = normalize_series(points)
    nan_steps = [point.step for point in ordered if math.isnan(point.value)]
    inf_steps = [point.step for point in ordered if math.isinf(point.value)]
    return {
        "nanCount": len(nan_steps), "infCount": len(inf_steps),
        "nanSteps": nan_steps, "infSteps": inf_steps,
        "hasInvalid": bool(nan_steps or inf_steps),
    }


def _finite(points: Iterable[Any]) -> list[CurvePoint]:
    return [point for point in normalize_series(points) if math.isfinite(point.value)]


def moving_statistics(points: Iterable[Any], window: int = 5) -> list[dict[str, float | None]]:
    """Compute trailing mean/std without filling missing values."""
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        raise ValueError("window must be a positive integer")
    ordered = normalize_series(points)
    output: list[dict[str, float | None]] = []
    for index, point in enumerate(ordered):
        values = [candidate.value for candidate in ordered[max(0, index - window + 1): index + 1] if math.isfinite(candidate.value)]
        mean = sum(values) / len(values) if values else None
        deviation = None
        if mean is not None:
            deviation = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
        output.append({"step": point.step, "mean": mean, "std": deviation, "count": len(values)})
    return output


def _interval(start: CurvePoint, end: CurvePoint, kind: str, *, count: int, detail: str) -> dict[str, float | int | str]:
    return {"kind": kind, "startStep": start.step, "endStep": end.step, "count": count, "detail": detail}


def detect_plateaus(points: Iterable[Any], *, window: int = 4, relative_tolerance: float = 0.01) -> list[dict[str, float | int | str]]:
    """Detect consecutive finite samples with low range.

    A plateau is evidence of a flat segment, not a training-stop instruction.
    The threshold scales with the segment's absolute median and has a small
    absolute floor so near-zero metrics can still be detected.
    """
    if window < 2 or relative_tolerance < 0:
        raise ValueError("window must be >= 2 and tolerance non-negative")
    ordered = normalize_series(points)
    plateaus: list[dict[str, float | int | str]] = []
    # Evaluate every window, then merge overlapping windows.  This avoids
    # emitting one duplicate interval per trailing sample and naturally
    # separates runs at NaN/Inf gaps.
    segment: list[CurvePoint] = []

    def flush(values: list[CurvePoint]) -> None:
        if len(values) < window:
            return
        windows: list[tuple[int, int]] = []
        for start in range(0, len(values) - window + 1):
            sample = values[start:start + window]
            sample_values = [entry.value for entry in sample]
            scale = max(abs(median(sample_values)), 1.0e-12)
            if max(sample_values) - min(sample_values) <= max(scale * relative_tolerance, 1.0e-12):
                end = start + window - 1
                if windows and start <= windows[-1][1] + 1:
                    windows[-1] = (windows[-1][0], end)
                else:
                    windows.append((start, end))
        for start, end in windows:
            plateaus.append(_interval(values[start], values[end], "plateau", count=end - start + 1, detail="low_range"))

    for point in ordered:
        if math.isfinite(point.value):
            segment.append(point)
        else:
            flush(segment)
            segment = []
    flush(segment)
    return plateaus


def detect_spikes(points: Iterable[Any], *, z_threshold: float = 4.0) -> list[dict[str, float | int | str]]:
    """Detect robust outliers using median absolute deviation (MAD)."""
    if z_threshold <= 0:
        raise ValueError("z_threshold must be positive")
    ordered = normalize_series(points)
    finite = [point for point in ordered if math.isfinite(point.value)]
    if len(finite) < 3:
        return []
    center = median([point.value for point in finite])
    deviations = [abs(point.value - center) for point in finite]
    mad = median(deviations)
    # 1.4826 converts MAD to a normal-distribution sigma estimate.  For a
    # perfectly flat curve use a tiny scale and only flag actual differences.
    scale = max(1.4826 * mad, 1.0e-12)
    result = []
    for point in finite:
        robust_z = abs(point.value - center) / scale
        if robust_z >= z_threshold:
            result.append({"kind": "spike", "startStep": point.step, "endStep": point.step, "count": 1, "detail": "robust_z", "score": robust_z})
    return result


def _slope(points: list[CurvePoint]) -> float | None:
    if len(points) < 2:
        return None
    x_mean = sum(point.step for point in points) / len(points)
    y_mean = sum(point.value for point in points) / len(points)
    denominator = sum((point.step - x_mean) ** 2 for point in points)
    return None if denominator == 0 else sum((point.step - x_mean) * (point.value - y_mean) for point in points) / denominator


def summarize_curve(
    series: Iterable[Any], *, metric: str = "metric", source: str = "unknown",
    max_points: int = 200, moving_window: int = 5,
) -> CurveSummary:
    """Build a deterministic, evidence-oriented summary for one metric series."""
    ordered = normalize_series(series)
    sampled = downsample_series(ordered, max_points=max_points)
    finite = [point for point in ordered if math.isfinite(point.value)]
    nan_count = sum(math.isnan(point.value) for point in ordered)
    inf_count = sum(math.isinf(point.value) for point in ordered)
    coverage = len(finite) / len(ordered) if ordered else 0.0
    confidence = "high" if coverage >= 0.95 and len(finite) >= 3 else "medium" if coverage >= 0.5 and finite else "low" if finite else "unknown"
    anomalies: list[dict[str, Any]] = []
    invalid = detect_nan_inf(ordered)
    if invalid["hasInvalid"]:
        anomalies.append({"kind": "invalid", "steps": invalid["nanSteps"] + invalid["infSteps"], "detail": "nan_or_inf"})
    plateaus = detect_plateaus(ordered)
    spikes = detect_spikes(ordered)
    anomalies.extend(plateaus)
    anomalies.extend(spikes)
    return CurveSummary(
        metric=str(metric), source=str(source), points=[point.as_dict() for point in ordered],
        sampled_points=[point.as_dict() for point in sampled], first=finite[0].value if finite else None,
        last=finite[-1].value if finite else None, minimum=min((point.value for point in finite), default=None),
        maximum=max((point.value for point in finite), default=None), finite_count=len(finite),
        nan_count=nan_count, inf_count=inf_count, missing_count=len(ordered) - len(finite),
        slope=_slope(finite), moving=moving_statistics(ordered, window=moving_window),
        plateaus=plateaus, spikes=spikes, anomalies=anomalies, coverage=coverage,
        confidence=confidence, unknown=not bool(finite), range_start=ordered[0].step if ordered else None,
        range_end=ordered[-1].step if ordered else None,
    )


def analyze_curve(
    series_by_metric: Mapping[str, Iterable[Any]] | Iterable[Any], *, source: str = "unknown",
    max_points: int = 200,
) -> dict[str, Any]:
    """Summarize one or more metrics and provide a conservative status.

    No status is emitted as a training command.  ``unknown`` is returned when
    no finite evidence exists; otherwise the result only describes observed
    anomalies and trend evidence.
    """
    if isinstance(series_by_metric, Mapping):
        summaries = {str(name): summarize_curve(values, metric=str(name), source=source, max_points=max_points).as_dict() for name, values in sorted(series_by_metric.items(), key=lambda item: str(item[0]))}
    else:
        summary = summarize_curve(series_by_metric, source=source, max_points=max_points)
        summaries = {summary.metric: summary.as_dict()}
    finite = [item for item in summaries.values() if not item["unknown"]]
    invalid = [item for item in summaries.values() if item["nan_count"] or item["inf_count"]]
    status = "unknown" if not finite else "review" if invalid or any(item["anomalies"] for item in finite) else "stable"
    action = "unknown" if status == "unknown" else "review" if status == "review" else "continue"
    return {
        "state": status, "status": status, "decision": action, "summaries": summaries,
        "recommendation": {"action": action, "automaticStop": False, "userDecisionRequired": True},
        "evidence": {"source": source, "metrics": sorted(summaries), "missingMetrics": sorted(name for name, item in summaries.items() if item["unknown"])},
        "userDecisionRequired": True,
    }


def get_series(
    series: Iterable[Any], *, tags: Mapping[str, Any] | None = None,
    max_points: int = 200, metric: str = "metric", source: str = "unknown",
) -> dict[str, Any]:
    """Tool-shaped DTO for the ``metrics.get_series`` contract."""
    summary = summarize_curve(series, metric=metric, source=source, max_points=max_points)
    result = summary.as_dict()
    result["tags"] = dict(tags or {})
    result["points"] = result["sampled_points"]
    return result


__all__ = ["CurvePoint", "CurveSummary", "normalize_series", "downsample_series", "detect_nan_inf", "moving_statistics", "detect_plateaus", "detect_spikes", "summarize_curve", "analyze_curve", "get_series"]

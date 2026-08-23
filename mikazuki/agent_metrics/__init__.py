"""Deterministic metrics and artifact-comparison services for the Agent.

The package deliberately contains no model calls and no filesystem mutation.
It produces evidence-oriented summaries that a Host Tool can expose to the
optional Agent plugin.  Missing evidence is represented explicitly rather
than being converted to a zero score.
"""

from .analysis import (
    CurvePoint,
    CurveSummary,
    analyze_curve,
    detect_nan_inf,
    detect_plateaus,
    detect_spikes,
    downsample_series,
    get_series,
    moving_statistics,
    summarize_curve,
)
from .artifacts import (
    ArtifactComparison,
    ArtifactRecord,
    FixedComparisonProtocol,
    Recommendation,
    compare_artifacts,
    get_comparison_set,
    list_artifacts,
    recommend_artifacts,
)

__all__ = [
    "CurvePoint", "CurveSummary", "analyze_curve", "summarize_curve",
    "downsample_series", "get_series", "moving_statistics", "detect_nan_inf",
    "detect_plateaus", "detect_spikes", "ArtifactRecord",
    "FixedComparisonProtocol", "ArtifactComparison", "Recommendation",
    "list_artifacts", "compare_artifacts", "get_comparison_set", "recommend_artifacts",
]

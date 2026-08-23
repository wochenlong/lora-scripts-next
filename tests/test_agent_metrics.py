from __future__ import annotations

import math

import pytest

from mikazuki.agent_metrics import (
    ArtifactRecord,
    FixedComparisonProtocol,
    analyze_curve,
    compare_artifacts,
    detect_nan_inf,
    detect_plateaus,
    detect_spikes,
    downsample_series,
    get_comparison_set,
    get_series,
    list_artifacts,
    recommend_artifacts,
    summarize_curve,
)


def test_curve_summary_sorts_downsamples_and_keeps_invalid_evidence():
    values = [{"step": step, "value": value} for step, value in [(5, 1.0), (1, 0.5), (2, float("nan")), (3, 0.5), (4, float("inf"))]]
    summary = summarize_curve(values, metric="loss", source="fixture", max_points=3)
    assert [point["step"] for point in summary.points] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert [point["step"] for point in summary.sampled_points] == [1.0, 3.0, 5.0]
    assert summary.nan_count == 1 and summary.inf_count == 1
    assert summary.missing_count == 2
    assert summary.range_start == 1.0 and summary.range_end == 5.0
    assert summary.confidence == "medium"
    assert summary.as_dict()["anomalies"]


def test_detectors_are_deterministic_and_do_not_fill_missing_values():
    plateau = detect_plateaus([(1, 1.0), (2, 1.001), (3, 1.0), (4, 1.0)])
    assert plateau and plateau[0]["kind"] == "plateau"
    spikes = detect_spikes([(1, 1.0), (2, 1.0), (3, 100.0), (4, 1.0), (5, 1.0)])
    assert [item["startStep"] for item in spikes] == [3.0]
    invalid = detect_nan_inf([(1, float("nan")), (2, float("inf")), (3, 1.0)])
    assert invalid["hasInvalid"] and invalid["nanSteps"] == [1.0]
    assert [item.step for item in downsample_series([(i, i) for i in range(10)], 4)] == [0.0, 3.0, 6.0, 9.0]


def test_curve_analysis_is_conservative_when_data_is_unknown():
    result = analyze_curve({"loss": [(1, float("nan"))], "quality": []})
    assert result["state"] == "unknown"
    assert result["userDecisionRequired"] is True
    assert result["evidence"]["missingMetrics"] == ["loss", "quality"]


def test_fixed_comparison_keeps_failed_prompts_and_same_conditions():
    protocol = FixedComparisonProtocol(("front", "side"), 7, {"steps": 20, "cfg": 5.5})
    records = [ArtifactRecord("b", step=20), ArtifactRecord("a", step=10)]

    def render(record, prompt, seed, config):
        assert seed == 7
        assert config == {"steps": 20, "cfg": 5.5}
        if record.artifact_id == "b" and prompt == "side":
            return {"state": "failed", "failure": "fixture_timeout"}
        return {"state": "success", "imageId": f"{record.artifact_id}-{prompt}"}

    result = compare_artifacts(records, protocol, renderer=render)
    assert [item["artifactId"] for item in result.candidates] == ["a", "b"]
    assert result.candidates[1]["failed"] == 1
    assert result.coverage == pytest.approx(0.75)
    assert result.candidates[1]["results"][1]["failure"] == "fixture_timeout"
    assert get_comparison_set(records, protocol.as_dict())["protocol"]["protocolId"] == protocol.protocol_id
    assert get_series([(2, 2), (1, 1)], max_points=2)["points"][0]["step"] == 1.0
    assert list_artifacts(records)[0]["artifactId"] == "a"


def test_recommendation_uses_locked_weights_and_missing_denominator():
    records = [
        ArtifactRecord("complete", metrics={"quality": 80, "overfitRisk": 20, "stability": 70, "efficiency": 60}),
        ArtifactRecord("partial", metrics={"quality": 95, "stability": 95}),
        ArtifactRecord("unknown", metrics={}),
    ]
    result = recommend_artifacts(records, top_k=3)
    assert result["weights"] == {"quality": 0.4, "overfitRisk": 0.25, "stability": 0.2, "efficiency": 0.15}
    # Missing dimensions reduce coverage/confidence, but are not converted to
    # zeroes; a strong partial record may therefore lead on available evidence.
    assert result["topK"][0]["artifactId"] == "partial"
    partial = next(item for item in result["topK"] if item["artifactId"] == "partial")
    assert partial["missingDimensions"] == ["overfitRisk", "efficiency"]
    assert partial["coverage"] == pytest.approx(0.6)
    assert partial["score"] == pytest.approx((0.4 * 95 + 0.2 * 95) / 0.6)
    assert result["deletionSupported"] is False
    assert all(item["evidence"]["userDecisionRequired"] for item in result["topK"])


def test_artifact_dto_does_not_expose_arbitrary_filesystem_paths():
    record = ArtifactRecord.from_mapping({"id": "safe", "metadata": {"path": "C:/private/model.safetensors", "label": "checkpoint"}, "metrics": {"quality": 50}})
    rendered = record.as_dict()
    assert "path" not in rendered["metadata"]
    assert rendered["metadata"]["label"] == "checkpoint"


def test_protocol_rejects_more_than_four_prompts_and_five_artifact_limit():
    with pytest.raises(ValueError):
        FixedComparisonProtocol(("a", "b", "c", "d", "e"), 1, {})
    protocol = FixedComparisonProtocol(("a",), 1, {})
    with pytest.raises(ValueError):
        compare_artifacts([ArtifactRecord(str(index)) for index in range(6)], protocol)

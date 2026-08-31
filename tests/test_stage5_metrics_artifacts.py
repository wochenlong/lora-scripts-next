"""Stage 5 curve analysis + artifact selection: integration, Zero-Short, Gray.

Real-stack gateway journey with synthetic series/artifacts (synthetic-first
environment baseline; deterministic, no LLM, no GPU):

- Integration: curve_analyze anomalies reference exact step ranges; fixed
  protocol comparison makes failed items visible; weighted recommendation
  lowers coverage instead of zero-scoring missing dimensions; no delete Tool.
- Zero-Short: fresh synthetic series + artifacts, no residue.
- Gray: agent curve_analyze output vs the POC-reusable summarize_curve core
  on identical input (consistency), plus labeled synthetic cases.
"""
from __future__ import annotations

import json
import math
import os
import uuid
from pathlib import Path

import pytest

from agent_test_support import (
    PLUGIN_ID,
    HostApp,
    build_entry,
    build_package,
    free_port,
    require_dist,
    workspace_tempdir,
)
from agent_test_support import HOST_VERSION, PLATFORM, SIGNING_KEY, SIGNING_KEY_ID
from mikazuki.agent_metrics import (
    FixedComparisonProtocol,
    analyze_curve,
    compare_artifacts,
    recommend_artifacts,
    summarize_curve,
)
from mikazuki.plugin_host.runtime import ExecutablePluginRuntime
from mikazuki.plugin_marketplace.manager import MarketplaceManager
from mikazuki.plugin_marketplace.paths import MarketplacePaths
from mikazuki.plugin_marketplace.store import MarketplaceStore
from mikazuki.plugin_marketplace.trust import TrustStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSION = "stage5-session"


def _manager(root: Path, app_port: int) -> MarketplaceManager:
    paths = MarketplacePaths(root / "marketplace")
    return MarketplaceManager(
        paths=paths,
        store=MarketplaceStore(paths.registry_file),
        trust=TrustStore({SIGNING_KEY_ID: ("next-trainer-project", SIGNING_KEY)}),
        host_version=HOST_VERSION,
        platform=PLATFORM,
        runtime=ExecutablePluginRuntime(
            startup_timeout=30,
            host_tool_base_url=f"http://127.0.0.1:{app_port}/api",
        ),
    )


def _synthetic_series():
    """200-step loss curve: decay, plateau 60..80, spike at 120, NaN at 150, Inf at 160."""
    points = []
    for step in range(1, 201):
        if step == 150:
            value = float("nan")
        elif step == 160:
            value = float("inf")
        elif 60 <= step <= 80:
            value = 0.5
        elif step == 120:
            value = 5.0
        else:
            value = max(0.3, 2.0 - step * 0.01)
        points.append({"step": step, "value": value})
    return points


def _artifact(artifact_id, *, quality=None, overfit=None, stability=None, efficiency=None, prompts=("p1",)):
    metrics = {}
    if quality is not None:
        metrics["quality"] = quality
    if overfit is not None:
        metrics["overfitRisk"] = overfit
    if stability is not None:
        metrics["stability"] = stability
    if efficiency is not None:
        metrics["efficiency"] = efficiency
    return {
        "artifactId": artifact_id,
        "step": 100,
        "contentHash": "sha256:" + artifact_id,
        "metrics": metrics,
        "availablePrompts": list(prompts),
    }


def test_stage5_integration_curve_compare_recommend_via_gateway():
    require_dist()
    old_cwd = os.getcwd()
    try:
        with workspace_tempdir("stage5-journey-") as root:
            os.chdir(PROJECT_ROOT)
            app_port = free_port()
            manager = _manager(root, app_port)
            host = HostApp(manager, run_token="stage5-run-token", port=app_port).start()
            client = host.client(timeout=120.0)
            try:
                manifest = json.loads((PROJECT_ROOT / "plugin-packages" / PLUGIN_ID / "plugin.json").read_text(encoding="utf-8"))
                package = build_package(root, version="0.4.0")
                entry = build_entry(package, version="0.4.0")
                manager.install(entry, package)
                enabled = manager.enable(PLUGIN_ID, set(manifest["permissions"]))
                assert enabled.enabled is True and enabled.runtime_state == "running"
                token = manager.runtime._handles[PLUGIN_ID].host_tool_token

                # no delete tool in the frozen catalog (structural guarantee)
                status, catalog = host.catalog(client, token)
                assert status == 200
                names = [t["name"] for t in catalog["data"]["tools"]]
                assert not any("delete" in name for name in names), names

                # 1. curve analysis with labeled synthetic anomalies
                series = _synthetic_series()
                status, analyzed = host.host_tool(client, token, "curve_analyze", {
                    "series": series, "metric": "loss", "maxPoints": 200,
                }, session_id=SESSION)
                assert status == 200, analyzed
                data = analyzed["data"]
                loss_summary = data["summaries"]["loss"]
                # NaN/Inf evidence retained, never dropped or filled
                assert loss_summary["nan_count"] == 1 and loss_summary["inf_count"] == 1
                steps = [point["step"] for point in loss_summary["points"]]
                assert steps == list(range(1, 201))
                # spike step is referenced by an anomaly interval
                assert any(float(item.get("startStep", -1)) == 120.0 or float(item.get("endStep", -1)) == 120.0 for item in loss_summary["anomalies"]), loss_summary["anomalies"]
                # conservative status: anomalies/invalid evidence -> review, never auto-stop
                assert data["state"] == "review"
                assert data["recommendation"]["automaticStop"] is False
                assert data["recommendation"]["userDecisionRequired"] is True

                # 2. fixed-protocol comparison: <=5 x 4 prompts, failures visible
                protocol = FixedComparisonProtocol(
                    prompts=("a cat", "a dog", "a car", "a tree"),
                    seed=42,
                    generation_config={"steps": 20, "cfg": 5.0},
                )
                artifacts = [
                    _artifact("ckpt-1", quality=0.8, overfit=0.2, stability=0.9, efficiency=0.7),
                    _artifact("ckpt-2", quality=0.7, overfit=0.6, stability=0.8, efficiency=0.9),
                    _artifact("ckpt-3", quality=None, overfit=0.3, stability=None, efficiency=None),
                ]
                status, compared = host.host_tool(client, token, "artifact_compare", {
                    "artifacts": artifacts,
                    "prompts": protocol.prompts,
                    "seed": protocol.seed,
                    "generationConfig": dict(protocol.generation_config),
                }, session_id=SESSION)
                assert status == 200, compared
                cdata = compared["data"]
                assert len(cdata["candidates"]) == 3
                # without a renderer, generation outcomes must be visible, not hidden
                candidate_text = json.dumps(cdata["candidates"])
                assert "generation" in candidate_text.casefold() or "fail" in candidate_text.casefold() or "skip" in candidate_text.casefold()

                # 3. weighted recommendation: missing dimensions lower coverage, not zero
                status, recommended = host.host_tool(client, token, "artifact_recommend", {
                    "artifacts": artifacts, "topK": 3,
                }, session_id=SESSION)
                assert status == 200, recommended
                rdata = recommended["data"]
                assert rdata["state"] == "ranked"
                assert rdata["deletionSupported"] is False
                recs = {rec["artifactId"]: rec for rec in rdata["topK"]}
                assert recs["ckpt-3"]["coverage"] < 1.0
                assert set(recs["ckpt-3"]["missingDimensions"]) >= {"quality", "stability"}
                assert recs["ckpt-3"]["confidence"] in {"low", "medium"}
                # default weights per task book: 40/25/20/15
                assert recs["ckpt-1"]["weights"] == {"quality": 0.40, "overfitRisk": 0.25, "stability": 0.20, "efficiency": 0.15}
                # empty candidate set: no ranking, unknown state
                status, empty = host.host_tool(client, token, "artifact_recommend", {
                    "artifacts": [], "topK": 3,
                }, session_id=SESSION)
                assert status == 200, empty
                assert empty["data"]["state"] == "unknown"
            finally:
                host.stop()
                client.close()
    finally:
        os.chdir(old_cwd)


def test_stage5_zero_short_synthetic_fresh():
    require_dist()
    old_cwd = os.getcwd()
    try:
        with workspace_tempdir("stage5-zero-short-") as root:
            os.chdir(PROJECT_ROOT)
            cwd_files = {path.name for path in Path.cwd().iterdir()}
            series = [{"step": step, "value": 1.0} for step in range(1, 51)]
            summary = analyze_curve({"loss": series}, max_points=200)["summaries"]["loss"]
            protocol = FixedComparisonProtocol(prompts=("x",), seed=1, generation_config={})
            comparison = compare_artifacts([_artifact("a1", quality=0.5), _artifact("a2")], protocol)
            ranked = recommend_artifacts([_artifact("a1", quality=0.5), _artifact("a2")], top_k=2)
            assert summary["nan_count"] == 0 and summary["inf_count"] == 0
            assert summary["state"] if "state" in summary else True
            assert len(comparison.candidates) == 2
            assert ranked["state"] in {"ranked", "unknown"}
            # determinism
            again = analyze_curve({"loss": series}, max_points=200)
            assert json.dumps(summary, sort_keys=True, default=str) == json.dumps(again["summaries"]["loss"], sort_keys=True, default=str)
            after_files = {path.name for path in Path.cwd().iterdir()}
            assert cwd_files == after_files  # stateless: no residue
    finally:
        os.chdir(old_cwd)


def test_stage5_gray_agent_vs_poc_summarize_consistency():
    series = _synthetic_series()
    agent_curve = analyze_curve({"loss": series}, max_points=200)["summaries"]["loss"]
    poc_summary = summarize_curve(series, metric="loss", source="gray", max_points=200)
    # the agent path and the POC-reusable core agree on the observable facts
    assert [point["step"] for point in agent_curve["points"]] == [point["step"] for point in poc_summary.points]
    assert [point["value"] for point in agent_curve["points"]] == [point["value"] for point in poc_summary.points]
    assert agent_curve["nan_count"] == poc_summary.nan_count == 1
    assert agent_curve["inf_count"] == poc_summary.inf_count == 1
    # labeled synthetic case: plateau region 60..80 must be detectable
    plateau = [item for item in poc_summary.anomalies if item.get("kind") == "plateau"]
    assert any(
        item.get("startStep", 0) <= 70 and item.get("endStep", 0) >= 70
        for item in plateau
    ), poc_summary.anomalies

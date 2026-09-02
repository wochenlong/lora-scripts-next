from __future__ import annotations

import json

from mikazuki.agent_metrics import FixedComparisonProtocol, HttpArtifactRenderer, compare_artifacts, get_configured_renderer

ARTIFACT = {"artifactId": "ckpt-0001", "step": 100, "contentHash": "sha256:abc", "metrics": {"quality": 0.8}}
PROMPTS = ("a girl in a hat",)
SEED = 42
CONFIG = {"steps": 20}


def test_get_configured_renderer_env(monkeypatch):
    monkeypatch.delenv("MIKAZUKI_ARTIFACT_RENDERER_URL", raising=False)
    assert get_configured_renderer() is None
    monkeypatch.setenv("MIKAZUKI_ARTIFACT_RENDERER_URL", "http://127.0.0.1:8188/render")
    monkeypatch.setenv("MIKAZUKI_ARTIFACT_RENDERER_KEY", "k")
    monkeypatch.setenv("MIKAZUKI_ARTIFACT_RENDERER_BASE_MODEL", "anima")
    renderer = get_configured_renderer()
    assert renderer is not None
    assert renderer.url == "http://127.0.0.1:8188/render"
    assert renderer.api_key == "k"
    assert renderer.base_model == "anima"


def test_renderer_success_carries_image_payload():
    transport = lambda url, headers, body: (200, {"state": "success", "imageB64": "QUJD", "contentHash": "sha256:out", "sizeBytes": 123, "metadata": {"model": "anima"}})
    renderer = HttpArtifactRenderer(url="http://x", transport=transport)
    result = renderer(ARTIFACT, "a girl", SEED, CONFIG)
    assert result["state"] == "success"
    assert result["imageB64"] == "QUJD"
    assert result["metadata"] == {"model": "anima"}


def test_renderer_request_body_contract():
    captured = {}

    def transport(url, headers, body):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json.loads(body)
        return 200, {"state": "success"}

    renderer = HttpArtifactRenderer(url="http://x", api_key="k", base_model="anima", transport=transport)
    renderer(ARTIFACT, "a girl", SEED, CONFIG)
    body = captured["body"]
    assert body["artifact"]["artifactId"] == "ckpt-0001"
    assert body["artifact"]["contentHash"] == "sha256:abc"
    assert body["prompt"] == "a girl"
    assert body["seed"] == SEED
    assert body["generationConfig"] == CONFIG
    assert body["baseModel"] == "anima"
    assert captured["headers"]["Authorization"] == "Bearer k"


def test_renderer_failed_and_invalid_responses():
    renderer = HttpArtifactRenderer(url="http://x", transport=lambda *a: (200, {"state": "failed", "failure": "out_of_video_memory"}))
    assert renderer(ARTIFACT, "p", SEED, CONFIG)["failure"] == "out_of_video_memory"
    renderer = HttpArtifactRenderer(url="http://x", transport=lambda *a: (500, {}))
    assert renderer(ARTIFACT, "p", SEED, CONFIG)["state"] == "failed"
    renderer = HttpArtifactRenderer(url="http://x", transport=lambda *a: (200, "not-a-dict"))
    assert renderer(ARTIFACT, "p", SEED, CONFIG)["failure"] == "renderer_invalid_response"


def test_compare_artifacts_with_renderer_computes_coverage():
    protocol = FixedComparisonProtocol(PROMPTS, SEED, CONFIG)
    renderer = HttpArtifactRenderer(url="http://x", transport=lambda *a: (200, {"state": "success", "imageB64": "x"}))
    result = compare_artifacts([ARTIFACT], protocol, renderer=renderer)
    assert result.coverage == 1.0
    assert result.confidence == "high"
    assert result.candidates[0]["results"][0]["state"] == "success"


def test_compare_artifacts_without_renderer_reports_unavailable():
    protocol = FixedComparisonProtocol(PROMPTS, SEED, CONFIG)
    result = compare_artifacts([ARTIFACT], protocol)
    assert result.candidates[0]["results"][0]["state"] == "failed"
    assert result.candidates[0]["results"][0]["failure"] == "renderer_unavailable"
    assert result.coverage == 0.0

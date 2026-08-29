from __future__ import annotations

import json
from pathlib import Path

import pytest

from mikazuki.agent_dataset import DatasetReviewError, inventory_dataset, review_images
from mikazuki.agent_dataset.remote_reviewer import (
    BridgeVisionReviewer,
    _extract_json_object,
    _normalize_findings,
    get_configured_reviewer,
)

VALID_ANSWER = {
    "caption_match": "ok",
    "visual_issues": ["blurry"],
    "identity_notes": "consistent hair color",
    "caption_suggestion": "add: standing pose",
    "severity": "minor",
}


def _ok_transport(answer: str | None = None, status: int = 200):
    payload = {"choices": [{"message": {"content": answer if answer is not None else json.dumps(VALID_ANSWER)}}]}
    calls = []

    def transport(url, api_key, model, body):
        calls.append((url, api_key, model, body))
        return status, payload

    return transport, calls


def _small_image(path: Path) -> None:
    from PIL import Image

    image = Image.new("RGB", (32, 24), (120, 60, 20))
    image.save(path)


def test_extract_json_object_plain_and_fenced():
    assert _extract_json_object('{"a": 1}') == {"a": 1}
    assert _extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json_object('Here is the result:\n{"a": 1}\nHope that helps.') == {"a": 1}
    with pytest.raises(ValueError):
        _extract_json_object("no json here")


def test_normalize_findings_valid():
    result = _normalize_findings(VALID_ANSWER, "a girl")
    assert result["captionMatch"] == "ok"
    assert result["visualIssues"] == ["blurry"]
    assert result["severity"] == "minor"
    assert result["captionUnderReview"] == "a girl"


def test_normalize_findings_rejects_bad_values():
    with pytest.raises(ValueError):
        _normalize_findings({"caption_match": "maybe", "visual_issues": [], "severity": "ok"}, None)
    with pytest.raises(ValueError):
        _normalize_findings({"caption_match": "ok", "visual_issues": "blurry", "severity": "ok"}, None)
    with pytest.raises(ValueError):
        _normalize_findings({"caption_match": "ok", "visual_issues": [], "severity": "apocalyptic"}, None)


def test_normalize_findings_filters_unknown_issues():
    result = _normalize_findings({"caption_match": "ok", "visual_issues": ["blurry", "alien_beam"], "severity": "ok"}, None)
    assert result["visualIssues"] == ["blurry"]


def test_get_configured_reviewer_env(monkeypatch):
    monkeypatch.delenv("MIKAZUKI_VISION_REVIEW_KEY", raising=False)
    assert get_configured_reviewer() is None
    monkeypatch.setenv("MIKAZUKI_VISION_REVIEW_KEY", "test-key")
    reviewer = get_configured_reviewer()
    assert reviewer is not None
    assert reviewer.capability.vision is True
    assert reviewer.capability.model == "Qwen3.8-27B"
    monkeypatch.setenv("MIKAZUKI_VISION_REVIEW_MODEL", "other-model")
    monkeypatch.setenv("MIKAZUKI_VISION_REVIEW_URL", "http://127.0.0.1:9999/v1/chat/completions")
    reviewer = get_configured_reviewer()
    assert reviewer.model == "other-model"
    assert reviewer.url == "http://127.0.0.1:9999/v1/chat/completions"


def test_unbound_caller_requires_root():
    reviewer = BridgeVisionReviewer(url="http://x", api_key="k", model="m")
    with pytest.raises(DatasetReviewError) as exc:
        reviewer(None, None)
    assert exc.value.code == "REVIEW_ROOT_REQUIRED"


def test_review_file_success_and_strict_parsing(tmp_path: Path):
    image = tmp_path / "a.png"
    _small_image(image)
    from mikazuki.agent_dataset import InventoryItem

    item = InventoryItem(item_id="i1", relative_path="a.png", kind="image", bytes=1, content_hash=None, caption_text="a girl")
    transport, calls = _ok_transport()
    reviewer = BridgeVisionReviewer(url="http://x", api_key="k", model="m", transport=transport)
    result = reviewer.review_file(image, item)
    assert result["captionMatch"] == "ok"
    assert calls[0][1] == "k"
    assert calls[0][2] == "m"
    # the request body carries the image data-url and the caption prompt
    body = calls[0][3]
    content = body["messages"][0]["content"]
    assert any(part.get("type") == "image_url" and "data:image/jpeg;base64," in part["image_url"]["url"] for part in content)
    assert "a girl" in json.dumps(body)


def test_review_file_garbage_answer_raises():
    image = Path(__file__).parent / "test_agent_vision_reviewer.py"  # any existing file triggers decode fail first
    # use a real image so we reach the parse stage
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "a.png"
        _small_image(img)
        from mikazuki.agent_dataset import InventoryItem

        item = InventoryItem(item_id="i1", relative_path="a.png", kind="image", bytes=1, content_hash=None, caption_text="x")
        transport, _ = _ok_transport(answer="I cannot output JSON today.")
        reviewer = BridgeVisionReviewer(url="http://x", api_key="k", model="m", transport=transport)
        with pytest.raises((ValueError, DatasetReviewError)):
            reviewer.review_file(img, item)


def test_review_file_retries_once_on_503(tmp_path: Path):
    with __import__("tempfile").TemporaryDirectory() as td:
        img = Path(td) / "a.png"
        _small_image(img)
        from mikazuki.agent_dataset import InventoryItem

        item = InventoryItem(item_id="i1", relative_path="a.png", kind="image", bytes=1, content_hash=None, caption_text="x")
        states = iter([503, 200])

        def transport(url, api_key, model, body):
            status = next(states)
            if status == 503:
                return status, {}
            return status, {"choices": [{"message": {"content": json.dumps(VALID_ANSWER)}}]}

        sleeps = []
        reviewer = BridgeVisionReviewer(url="http://x", api_key="k", model="m", transport=transport, sleep=sleeps.append)
        result = reviewer.review_file(img, item)
        assert result["captionMatch"] == "ok"
        assert len(sleeps) == 1


def test_review_file_http_error_is_domain_error(tmp_path: Path):
    with __import__("tempfile").TemporaryDirectory() as td:
        img = Path(td) / "a.png"
        _small_image(img)
        from mikazuki.agent_dataset import InventoryItem

        item = InventoryItem(item_id="i1", relative_path="a.png", kind="image", bytes=1, content_hash=None, caption_text="x")
        reviewer = BridgeVisionReviewer(url="http://x", api_key="k", model="m", transport=lambda *a: (401, {}), sleep=lambda s: None)
        with pytest.raises(DatasetReviewError) as exc:
            reviewer.review_file(img, item)
        assert exc.value.code == "REMOTE_REVIEW_HTTP"


def test_review_images_end_to_end_with_bound_reviewer(tmp_path: Path):
    (tmp_path / "a.png").parent.mkdir(parents=True, exist_ok=True)
    _small_image(tmp_path / "a.png")
    (tmp_path / "a.txt").write_text("a girl in a hat", encoding="utf-8")
    inventory = inventory_dataset(tmp_path)
    image = inventory.images[0]
    transport, _ = _ok_transport()
    reviewer = BridgeVisionReviewer(url="http://x", api_key="k", model="m", transport=transport).with_root(inventory.root)
    report = review_images(inventory, [image], reviewer.capability, reviewer)
    assert report.status == "complete"
    assert report.reviewed_images == 1
    finding = report.results[0].findings[0]
    assert finding["captionMatch"] == "ok"
    assert finding["captionUnderReview"] == "a girl in a hat"

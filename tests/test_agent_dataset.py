from __future__ import annotations

import base64
import json

import pytest

from mikazuki.agent_dataset import (
    ActiveModelCapability,
    CaptionOverlay,
    DatasetReviewError,
    inventory_dataset,
    review_images,
    select_review_sample,
)


# A tiny valid 1x1 PNG, kept as a fixture rather than a model/runtime asset.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _dataset(tmp_path):
    root = tmp_path / "dataset"
    root.mkdir()
    (root / "one.png").write_bytes(PNG)
    (root / "one.txt").write_text("one subject, blue eyes\n", encoding="utf-8")
    (root / "duplicate.png").write_bytes(PNG)
    (root / "other.png").write_bytes(PNG + b"x")
    (root / "other.txt").write_text("other subject\n", encoding="utf-8")
    return root


def test_inventory_is_sorted_deterministic_and_reports_duplicates(tmp_path):
    root = _dataset(tmp_path)
    first = inventory_dataset(root)
    second = inventory_dataset(root)
    assert first.scan_hash == second.scan_hash
    assert [item.relative_path for item in first.files] == sorted(item.relative_path for item in first.files)
    assert first.total_bytes == sum(item.bytes for item in first.files)
    assert any(set(group) == {"one.png", "duplicate.png"} for group in first.duplicate_groups)
    one = next(item for item in first.images if item.relative_path == "one.png")
    assert one.caption_path == "one.txt"
    assert one.caption_text.startswith("one subject")
    assert one.width == 1 and one.height == 1
    assert first.caption_distribution["withCaption"] == 2


def test_sampling_and_text_only_model_never_fabricate_visual_review(tmp_path):
    inventory = inventory_dataset(_dataset(tmp_path))
    sample = select_review_sample(inventory, limit=2)
    capability = ActiveModelCapability("arbitrary-active-model", vision=False, capabilities=("text",))
    report = review_images(inventory, sample, capability)
    assert report.status == "MODEL_CAPABILITY_UNAVAILABLE"
    assert report.reviewed_images == 0
    assert report.unreviewed_images == len(inventory.images)
    assert all(item.status == "unavailable" and item.reason == "MODEL_CAPABILITY_UNAVAILABLE" for item in report.results)


def test_image_capable_review_uses_only_caller_remote_reviewer(tmp_path):
    inventory = inventory_dataset(_dataset(tmp_path))
    sample = select_review_sample(inventory, limit=1)
    capability = ActiveModelCapability("active", vision=True, capabilities=("text", "image"))
    seen = []

    def reviewer(item, active):
        seen.append((item.relative_path, active.model))
        return {"kind": "caption_alignment", "label": "pass"}

    report = review_images(inventory, sample, capability, reviewer)
    assert report.status == "complete"
    assert report.reviewed_images == 1
    assert seen == [(sample[0].relative_path, "active")]
    assert report.results[0].findings[0]["label"] == "pass"


def test_caption_overlay_requires_ticket_binds_hash_and_restores(tmp_path):
    root = _dataset(tmp_path)
    overlay = CaptionOverlay(root)
    change = overlay.stage("one.txt", "one subject, revised\n", reason="remove ambiguity")
    change_set = overlay.build_change_set([change])
    with pytest.raises(DatasetReviewError) as error:
        overlay.commit(change_set)
    assert error.value.code == "DATASET_CONFIRMATION_REQUIRED"
    with pytest.raises(DatasetReviewError) as error:
        overlay.commit(change_set, confirmation_ticket={"state": "approved", "changeSetHash": "sha256:wrong"})
    assert error.value.code == "DATASET_CONFIRMATION_MISMATCH"
    result = overlay.commit(change_set, confirmation_ticket={"state": "approved", "changeSetHash": change_set.change_set_hash})
    assert result.state == "committed"
    assert (root / "one.txt").read_text(encoding="utf-8") == "one subject, revised\n"
    restored = overlay.restore(result)
    assert restored.state == "restored"
    assert (root / "one.txt").read_text(encoding="utf-8") == "one subject, blue eyes\n"
    assert restored.restore_hashes["one.txt"].startswith("sha256:")
    # Review artifacts are not mistaken for dataset captions on a subsequent scan.
    assert all(".agent-dataset-review/" not in item.relative_path for item in inventory_dataset(root).files)


def test_caption_scope_rejects_images_paths_and_concurrent_source_change(tmp_path):
    root = _dataset(tmp_path)
    overlay = CaptionOverlay(root)
    for path in ("one.png", "../outside.txt", "C:/outside.txt", "one.txt:secret"):
        with pytest.raises(DatasetReviewError) as error:
            overlay.stage(path, "changed")
        assert error.value.code in {"DATASET_TEXT_SCOPE_FORBIDDEN", "DATASET_PATH_ESCAPE", "DATASET_FILE_NOT_FOUND"}
    with pytest.raises(DatasetReviewError) as error:
        overlay.stage("one.txt", "   \n")
    assert error.value.code == "DATASET_CAPTION_DELETE_FORBIDDEN"
    change_set = overlay.build_change_set([overlay.stage("one.txt", "new\n")])
    (root / "one.txt").write_text("concurrent\n", encoding="utf-8")
    with pytest.raises(DatasetReviewError) as error:
        overlay.commit(change_set, confirmation_ticket={"state": "approved", "changeSetHash": change_set.change_set_hash})
    assert error.value.code == "DATASET_SOURCE_CHANGED"


def test_backup_cannot_escape_review_overlay(tmp_path):
    root = _dataset(tmp_path)
    overlay = CaptionOverlay(root)
    change_set = overlay.build_change_set([overlay.stage("one.txt", "new")])
    with pytest.raises(DatasetReviewError) as error:
        overlay.commit(
            change_set,
            confirmation_ticket={"state": "approved", "changeSetHash": change_set.change_set_hash},
            backup_root=tmp_path / "outside-backups",
        )
    assert error.value.code == "DATASET_BACKUP_INVALID"


def test_change_set_contract_is_json_serializable(tmp_path):
    root = _dataset(tmp_path)
    overlay = CaptionOverlay(root)
    change_set = overlay.build_change_set([overlay.stage("one.txt", "new")])
    payload = change_set.as_dict()
    assert payload["changeSetHash"].startswith("sha256:")
    assert json.loads(json.dumps(payload, ensure_ascii=False))["changes"][0]["beforeHash"].startswith("sha256:")

import json
from pathlib import Path

from mikazuki.datasets.detect import MANIFEST_FILENAME, detect_dataset_type


def write_images(root: Path, rels, caption=False):
    for rel in rels:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"img")
        if caption:
            path.with_suffix(".txt").write_text("a caption", encoding="utf-8")


def flat_dataset(root: Path):
    write_images(root, ["a.png", "b.png"], caption=True)


def test_flat_image_dataset_with_repeats_subdir(tmp_path):
    flat_dataset(tmp_path)
    write_images(tmp_path, ["10_cat/c1.png", "10_cat/c2.png"])
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image"
    assert result["confidence"] == "detected"
    assert result["targets"] is None
    assert result["refs"] == []


def test_paired_subtrees_detect_edit_dataset(tmp_path):
    rels = ["1.png", "2.png", "3.png", "5_x/nested.png"]
    write_images(tmp_path / "targets", rels, caption=True)
    write_images(tmp_path / "ref", rels)
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image_edit"
    assert result["confidence"] == "detected"
    assert result["targets"] == "targets"
    assert result["refs"] == ["ref"]


def test_multiple_refs_sorted_by_name(tmp_path):
    rels = ["1.png", "2.png", "3.png"]
    write_images(tmp_path / "targets", rels, caption=True)
    write_images(tmp_path / "zzz", rels)
    write_images(tmp_path / "aaa", rels)
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image_edit"
    assert result["targets"] == "targets"
    assert result["refs"] == ["aaa", "zzz"]


def test_unpaired_subtrees_stay_image(tmp_path):
    write_images(tmp_path / "cat", ["1.png", "2.png", "3.png"], caption=True)
    write_images(tmp_path / "dog", ["a.png", "b.png", "c.png"], caption=True)
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image"
    assert result["confidence"] == "detected"


def test_identical_repeats_dirs_are_not_paired(tmp_path):
    rels = ["1.png", "2.png", "3.png"]
    write_images(tmp_path / "10_cat", rels, caption=True)
    write_images(tmp_path / "20_cat_backup", rels, caption=True)
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image"
    assert result["confidence"] == "detected"


def test_partial_overlap_detects_edit_dataset(tmp_path):
    write_images(tmp_path / "targets", ["1.png", "2.png", "3.png", "4.png", "5.png"], caption=True)
    write_images(tmp_path / "ref", ["1.png", "2.png", "3.png", "4.png", "extra.png"])
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image_edit"
    assert result["confidence"] == "detected"
    assert result["targets"] == "targets"
    assert result["refs"] == ["ref"]


def test_overlap_below_threshold_only_candidate(tmp_path):
    write_images(tmp_path / "targets", ["1.png", "2.png", "3.png", "4.png", "5.png"], caption=True)
    write_images(tmp_path / "ref", ["1.png", "2.png", "3.png", "x1.png", "x2.png", "x3.png", "x4.png", "x5.png"])
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image"
    assert result["confidence"] == "candidate"
    assert result["reason"]


def test_small_pairing_only_candidate(tmp_path):
    write_images(tmp_path / "targets", ["1.png", "2.png"], caption=True)
    write_images(tmp_path / "ref", ["1.png", "2.png"])
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image"
    assert result["confidence"] == "candidate"
    assert result["reason"]


def test_multiple_captioned_subtrees_ambiguous(tmp_path):
    rels = ["1.png", "2.png", "3.png"]
    write_images(tmp_path / "one", rels, caption=True)
    write_images(tmp_path / "two", rels, caption=True)
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image_edit"
    assert result["confidence"] == "ambiguous"
    assert result["targets"] is None


def test_no_captioned_subtree_ambiguous(tmp_path):
    rels = ["1.png", "2.png", "3.png"]
    write_images(tmp_path / "one", rels)
    write_images(tmp_path / "two", rels)
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image_edit"
    assert result["confidence"] == "ambiguous"
    assert result["targets"] is None


def test_partial_caption_marks_subtree_as_targets(tmp_path):
    rels = ["1.png", "2.png", "3.png"]
    write_images(tmp_path / "targets", rels)
    (tmp_path / "targets" / "1.txt").write_text("only one caption", encoding="utf-8")
    write_images(tmp_path / "ref", rels)
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image_edit"
    assert result["targets"] == "targets"
    assert result["refs"] == ["ref"]


def test_empty_dataset_is_image(tmp_path):
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image"
    assert result["confidence"] == "detected"


def test_manifest_override_wins(tmp_path):
    rels = ["1.png", "2.png", "3.png"]
    write_images(tmp_path / "targets", rels, caption=True)
    write_images(tmp_path / "ref", rels)
    (tmp_path / MANIFEST_FILENAME).write_text(json.dumps({"type": "image"}), encoding="utf-8")
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image"
    assert result["confidence"] == "override"


def test_manifest_override_roles(tmp_path):
    flat_dataset(tmp_path)
    manifest = {"type": "image_edit", "targets": "a", "refs": ["b", "a2"]}
    (tmp_path / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image_edit"
    assert result["confidence"] == "override"
    assert result["targets"] == "a"
    assert result["refs"] == ["b", "a2"]


def test_invalid_manifest_falls_back_to_detection(tmp_path):
    rels = ["1.png", "2.png", "3.png"]
    write_images(tmp_path / "targets", rels, caption=True)
    write_images(tmp_path / "ref", rels)
    (tmp_path / MANIFEST_FILENAME).write_text("{not json", encoding="utf-8")
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image_edit"
    assert result["confidence"] == "detected"


def test_unknown_manifest_type_falls_back(tmp_path):
    flat_dataset(tmp_path)
    (tmp_path / MANIFEST_FILENAME).write_text(json.dumps({"type": "pairs"}), encoding="utf-8")
    result = detect_dataset_type(tmp_path)
    assert result["type"] == "image"
    assert result["confidence"] == "detected"

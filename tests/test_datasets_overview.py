from pathlib import Path

from mikazuki.app.application import app
from mikazuki.datasets.stats import compute_overview


def write_images(root: Path, rels, caption=False):
    for rel in rels:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"img")
        if caption:
            path.with_suffix(".txt").write_text("caption", encoding="utf-8")


def test_image_dataset_overview_reports_type_and_null_pairing(tmp_path):
    dataset_dir = tmp_path / "ds"
    write_images(dataset_dir, ["a.png", "10_cat/b.png"], caption=True)

    overview = compute_overview(dataset_dir)

    assert overview["type"] == "image"
    assert overview["type_confidence"] == "detected"
    assert overview["targets"] is None
    assert overview["refs"] == []
    assert overview["file_count"] == 2
    assert overview["captioned_count"] == 2
    assert overview["paired_count"] is None
    assert overview["unpaired_count"] is None
    assert overview["orphan_ref_count"] is None


def test_edit_dataset_counts_targets_only_and_pairing(tmp_path):
    dataset_dir = tmp_path / "ds"
    write_images(dataset_dir / "targets", ["1.png", "2.png", "3.png", "4.png", "5.png"], caption=True)
    (dataset_dir / "targets" / "2.txt").unlink()
    write_images(dataset_dir / "ref", ["1.png", "2.png", "3.png", "4.png", "extra.png"])

    overview = compute_overview(dataset_dir)

    assert overview["type"] == "image_edit"
    assert overview["targets"] == "targets"
    assert overview["refs"] == ["ref"]
    assert overview["file_count"] == 5
    assert overview["captioned_count"] == 4
    assert overview["paired_count"] == 4
    assert overview["unpaired_count"] == 1
    assert overview["orphan_ref_count"] == 1


def test_ambiguous_edit_dataset_falls_back_to_whole_tree_counts(tmp_path):
    dataset_dir = tmp_path / "ds"
    write_images(dataset_dir / "one", ["1.png", "2.png", "3.png"], caption=True)
    write_images(dataset_dir / "two", ["1.png", "2.png", "3.png"], caption=True)

    overview = compute_overview(dataset_dir)

    assert overview["type"] == "image_edit"
    assert overview["type_confidence"] == "ambiguous"
    assert overview["targets"] is None
    assert overview["file_count"] == 6
    assert overview["captioned_count"] == 6
    assert overview["paired_count"] is None
    assert overview["unpaired_count"] is None
    assert overview["orphan_ref_count"] is None

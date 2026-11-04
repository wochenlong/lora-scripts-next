"""Regression tests for issue #332.

Submitting a flat ``train_data_dir`` together with a ``dataset_config`` toml used
to make ``validate_data_dir`` move every image into a generated ``N_zkz``
subdirectory. The toml's ``image_dir`` then pointed at an emptied folder,
sd-scripts logged one ``no images found`` warning, skipped the subset and trained
to completion on whatever was left -- so the run looked healthy while most of the
dataset was never seen.
"""

import sys
from pathlib import Path

import toml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mikazuki.utils import train_utils  # noqa: E402


def _make_flat_dataset(root: Path, count: int = 3, suffix: str = ".png") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        (root / f"{index:03d}{suffix}").write_bytes(b"")
        (root / f"{index:03d}.txt").write_text("1girl", encoding="utf-8")
    return root


def _write_dataset_config(path: Path, image_dirs) -> Path:
    payload = {
        "general": {"shuffle_caption": False},
        "datasets": [
            {
                "resolution": 1024,
                "subsets": [{"image_dir": str(d), "num_repeats": 2} for d in image_dirs],
            }
        ],
    }
    path.write_text(toml.dumps(payload), encoding="utf-8")
    return path


def test_auto_organize_off_leaves_images_where_the_dataset_config_expects_them(tmp_path):
    data_dir = _make_flat_dataset(tmp_path / "train")
    config = _write_dataset_config(tmp_path / "dataset.toml", [data_dir])

    assert train_utils.validate_data_dir(str(data_dir), auto_organize=False) is True

    # Nothing moved: no generated subdir, images still directly under data_dir.
    assert [p.name for p in data_dir.iterdir() if p.is_dir()] == []
    assert len(train_utils.get_total_images(str(data_dir), recursive=False)) == 3

    # And the toml the user handed us still resolves to a non-empty subset.
    ok, message = train_utils.validate_dataset_config(str(config))
    assert ok, message


def test_auto_organize_moves_json_captions_beside_images(tmp_path):
    data_dir = tmp_path / "train"
    data_dir.mkdir()
    (data_dir / "image1.png").write_bytes(b"")
    (data_dir / "image1.json").write_text(
        '{"character": "character name", "tags": ["smile"]}',
        encoding="utf-8",
    )
    (data_dir / "notes.json").write_text("{}", encoding="utf-8")

    assert train_utils.validate_data_dir(str(data_dir)) is True

    generated = [path for path in data_dir.iterdir() if path.is_dir()]
    assert len(generated) == 1
    subset = generated[0]
    image = subset / "image1.png"
    assert image.is_file()
    assert (subset / "image1.json").is_file()
    assert (data_dir / "notes.json").is_file()
    assert not (data_dir / "image1.json").exists()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor" / "sd-scripts"))
    from library.train_util import read_caption  # noqa: E402

    assert read_caption(str(image), ".txt", False, True) == "character name, smile"


def test_auto_organize_on_still_builds_the_n_repeat_subdir(tmp_path):
    data_dir = _make_flat_dataset(tmp_path / "train")

    assert train_utils.validate_data_dir(str(data_dir)) is True

    generated = [p for p in data_dir.iterdir() if p.is_dir()]
    assert len(generated) == 1
    assert generated[0].name.endswith("_zkz")
    assert len(train_utils.get_total_images(str(generated[0]), recursive=False)) == 3
    assert len(train_utils.get_total_images(str(data_dir), recursive=False)) == 0


def test_moving_images_under_a_dataset_config_is_what_breaks_training(tmp_path):
    """Pins the failure mode, so the guard above cannot be removed unnoticed."""
    data_dir = _make_flat_dataset(tmp_path / "train")
    config = _write_dataset_config(tmp_path / "dataset.toml", [data_dir])

    train_utils.validate_data_dir(str(data_dir), auto_organize=True)

    ok, message = train_utils.validate_dataset_config(str(config))
    assert ok is False
    assert "image_dir" in message


def test_existing_n_repeat_subdirs_are_never_touched(tmp_path):
    data_dir = tmp_path / "train"
    subset = _make_flat_dataset(data_dir / "10_girl")

    assert train_utils.validate_data_dir(str(data_dir), auto_organize=False) is True
    assert train_utils.validate_data_dir(str(data_dir), auto_organize=True) is True
    assert sorted(p.name for p in data_dir.iterdir()) == ["10_girl"]
    assert len(train_utils.get_total_images(str(subset), recursive=False)) == 3


def test_empty_data_dir_is_rejected_either_way(tmp_path):
    data_dir = tmp_path / "train"
    data_dir.mkdir()

    assert train_utils.validate_data_dir(str(data_dir), auto_organize=False) is False
    assert train_utils.validate_data_dir(str(data_dir), auto_organize=True) is False


def test_validate_dataset_config_rejects_missing_subset_dir(tmp_path):
    config = _write_dataset_config(tmp_path / "dataset.toml", [tmp_path / "nope"])

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok is False
    assert "nope" in message


def test_validate_dataset_config_rejects_subset_dir_without_images(tmp_path):
    good = _make_flat_dataset(tmp_path / "good")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "notes.txt").write_text("no images here", encoding="utf-8")
    config = _write_dataset_config(tmp_path / "dataset.toml", [good, bad])

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok is False
    assert "bad" in message
    assert "good" not in message


def test_validate_dataset_config_only_scans_the_subset_dir_itself(tmp_path):
    """sd-scripts' glob_images is non-recursive, so nested images do not count."""
    parent = tmp_path / "train"
    _make_flat_dataset(parent / "10_girl")
    config = _write_dataset_config(tmp_path / "dataset.toml", [parent])

    ok, _ = train_utils.validate_dataset_config(str(config))

    assert ok is False


def test_validate_dataset_config_accepts_webp_datasets(tmp_path):
    data_dir = _make_flat_dataset(tmp_path / "train", suffix=".webp")
    config = _write_dataset_config(tmp_path / "dataset.toml", [data_dir])

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok, message


def test_validate_dataset_config_resolves_relative_image_dir_from_cwd(tmp_path, monkeypatch):
    """sd-scripts resolves a relative image_dir against the trainer's cwd."""
    _make_flat_dataset(tmp_path / "train")
    config = _write_dataset_config(tmp_path / "dataset.toml", ["train"])
    monkeypatch.chdir(tmp_path)

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok, message


def test_validate_dataset_config_flags_relative_path_that_only_works_next_to_the_toml(tmp_path, monkeypatch):
    """Must fail, not pass: sd-scripts would resolve it from cwd and skip it."""
    _make_flat_dataset(tmp_path / "train")
    config = _write_dataset_config(tmp_path / "dataset.toml", ["train"])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok is False
    assert "绝对路径" in message


def test_validate_dataset_config_accepts_metadata_only_subsets(tmp_path):
    config = tmp_path / "dataset.toml"
    config.write_text(
        toml.dumps(
            {
                "datasets": [
                    {"resolution": 1024, "subsets": [{"metadata_file": str(tmp_path / "meta.json")}]}
                ]
            }
        ),
        encoding="utf-8",
    )

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok, message


def test_validate_dataset_config_rejects_config_without_subsets(tmp_path):
    config = tmp_path / "dataset.toml"
    config.write_text(toml.dumps({"general": {"resolution": 1024}}), encoding="utf-8")

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok is False
    assert "subsets" in message


def test_validate_dataset_config_rejects_missing_file(tmp_path):
    ok, message = train_utils.validate_dataset_config(str(tmp_path / "nope.toml"))

    assert ok is False
    assert "nope.toml" in message


def _write_toml_config(path: Path, subsets) -> Path:
    payload = {
        "general": {"shuffle_caption": False},
        "datasets": [{"resolution": 1024, "subsets": subsets}],
    }
    path.write_text(toml.dumps(payload), encoding="utf-8")
    return path


def test_validate_dataset_config_rejects_num_repeats_below_one(tmp_path):
    """sd-scripts logs one warning and ignores the whole subset when
    num_repeats < 1, so the subset silently never trains."""
    train = _make_flat_dataset(tmp_path / "train")
    config = _write_toml_config(
        tmp_path / "dataset.toml", [{"image_dir": str(train), "num_repeats": 0}]
    )

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok is False
    assert "num_repeats" in message


def test_validate_dataset_config_rejects_boolean_false_num_repeats(tmp_path):
    """TOML ``num_repeats = false`` parses to 0 and is silently skipped too."""
    train = _make_flat_dataset(tmp_path / "train")
    config = _write_toml_config(
        tmp_path / "dataset.toml", [{"image_dir": str(train), "num_repeats": False}]
    )

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok is False
    assert "num_repeats" in message


def test_validate_dataset_config_rejects_duplicated_image_dir(tmp_path):
    """sd-scripts keeps the first subset with a given image_dir and silently
    ignores later ones, no matter what else differs."""
    train = _make_flat_dataset(tmp_path / "train")
    config = _write_toml_config(
        tmp_path / "dataset.toml",
        [
            {"image_dir": str(train), "num_repeats": 1},
            {"image_dir": str(train), "num_repeats": 5},
        ],
    )

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok is False
    assert "重复" in message


def test_validate_dataset_config_rejects_duplicated_metadata_file(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text("{}", encoding="utf-8")
    config = _write_toml_config(
        tmp_path / "dataset.toml",
        [
            {"metadata_file": str(meta)},
            {"metadata_file": str(meta)},
        ],
    )

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok is False
    assert "重复" in message


def test_validate_dataset_config_skipped_subset_cannot_shadow_duplicate(tmp_path):
    """sd-scripts registers only subsets that survive the num_repeats check, so
    a subset skipped for num_repeats=0 does not make its twin a duplicate; the
    report must blame num_repeats, not duplication."""
    train = _make_flat_dataset(tmp_path / "train")
    config = _write_toml_config(
        tmp_path / "dataset.toml",
        [
            {"image_dir": str(train), "num_repeats": 0},
            {"image_dir": str(train), "num_repeats": 1},
        ],
    )

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok is False
    assert "num_repeats" in message
    assert "重复子集" not in message


def test_validate_dataset_config_accepts_distinct_dirs_without_num_repeats(tmp_path):
    """An omitted num_repeats defaults to 1 in sd-scripts, and two different
    directories are not duplicates."""
    first = _make_flat_dataset(tmp_path / "first")
    second = _make_flat_dataset(tmp_path / "second")
    config = _write_toml_config(
        tmp_path / "dataset.toml",
        [{"image_dir": str(first)}, {"image_dir": str(second)}],
    )

    ok, message = train_utils.validate_dataset_config(str(config))

    assert ok, message

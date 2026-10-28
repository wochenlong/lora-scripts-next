import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor" / "sd-scripts"))

from library.config_util import BlueprintGenerator, ConfigSanitizer, DreamBoothSubsetParams  # noqa: E402
from library.train_util import DreamBoothDataset, DreamBoothSubset, add_dataset_arguments, read_caption  # noqa: E402


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_structured_json_fields_are_flattened_in_documented_order(tmp_path):
    image = tmp_path / "image1.png"
    write_json(
        image.with_suffix(".json"),
        {
            "nl": "a natural language description",
            "environment": ["indoors", "window light"],
            "tags": ["short hair", "smile"],
            "appearance": ["red dress", "blue eyes"],
            "artist": "artist name",
            "series": "series name",
            "character": "character name",
            "count": 1,
            "quality": "masterpiece",
        },
    )

    caption = read_caption(str(image), ".txt", False, True)

    assert caption == (
        "masterpiece, 1, character name, series name, artist name, red dress, blue eyes, "
        "short hair, smile, indoors, window light, a natural language description"
    )


def test_json_is_preferred_over_text_caption(tmp_path):
    image = tmp_path / "image1.png"
    write_json(image.with_suffix(".json"), {"tags": ["from json"]})
    image.with_suffix(".txt").write_text("from text", encoding="utf-8")

    assert read_caption(str(image), ".txt", False, True) == "from json"


def test_text_caption_is_used_when_json_is_missing_or_empty(tmp_path):
    missing_json_image = tmp_path / "missing.png"
    missing_json_image.with_suffix(".txt").write_text("missing json fallback", encoding="utf-8")
    empty_json_image = tmp_path / "empty.png"
    write_json(empty_json_image.with_suffix(".json"), {"tags": [], "nl": "  "})
    empty_json_image.with_suffix(".txt").write_text("empty json fallback", encoding="utf-8")

    assert read_caption(str(missing_json_image), ".txt", False, True) == "missing json fallback"
    assert read_caption(str(empty_json_image), ".txt", False, True) == "empty json fallback"


def test_disabling_json_preference_preserves_text_only_behavior(tmp_path):
    image = tmp_path / "image1.png"
    write_json(image.with_suffix(".json"), {"tags": ["from json"]})
    image.with_suffix(".txt").write_text("from text", encoding="utf-8")

    assert read_caption(str(image), ".txt", False, False) == "from text"


def test_empty_json_without_text_fallback_is_reported_as_missing(tmp_path):
    image = tmp_path / "image1.png"
    write_json(image.with_suffix(".json"), {})

    assert read_caption(str(image), ".txt", False, True) is None


def test_face_detection_json_fallback_uses_original_image_name(tmp_path):
    image = tmp_path / "character_0_0_0_0.png"
    write_json(tmp_path / "character.json", {"character": "character name"})

    assert read_caption(str(image), ".txt", False, True) == "character name"


@pytest.mark.parametrize("content", ["{not json", '["not", "an", "object"]'])
def test_invalid_json_fails_with_file_path(tmp_path, content):
    image = tmp_path / "broken.png"
    caption_path = image.with_suffix(".json")
    caption_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="broken.json"):
        read_caption(str(image), ".txt", False, True)


def test_unsupported_json_field_value_fails_with_field_and_file_path(tmp_path):
    image = tmp_path / "broken.png"
    write_json(image.with_suffix(".json"), {"tags": [{"name": "nested"}]})

    with pytest.raises(ValueError) as error:
        read_caption(str(image), ".txt", False, True)

    assert "tags" in str(error.value)
    assert "broken.json" in str(error.value)


def test_prefer_json_caption_flows_from_cli_to_dreambooth_subset(tmp_path):
    parser = argparse.ArgumentParser()
    add_dataset_arguments(parser, True, True, True)
    args = parser.parse_args(["--prefer_json_caption", "--caption_extension", ".txt"])
    sanitizer = ConfigSanitizer(
        support_dreambooth=True,
        support_finetuning=False,
        support_controlnet=False,
        support_dropout=True,
    )
    user_config = {
        "datasets": [
            {
                "resolution": 1024,
                "subsets": [{"image_dir": str(tmp_path), "num_repeats": 1}],
            }
        ]
    }

    blueprint = BlueprintGenerator(sanitizer).generate(user_config, args)
    params = blueprint.dataset_group.datasets[0].subsets[0].params
    subset = DreamBoothSubset(**asdict(params))

    assert params.prefer_json_caption is True
    assert subset.prefer_json_caption is True
    assert subset.caption_extension == ".txt"


def test_dreambooth_dataset_loads_and_caches_json_caption(tmp_path):
    image_path = tmp_path / "image1.png"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(image_path)
    write_json(image_path.with_suffix(".json"), {"character": "character name", "tags": ["smile"]})
    subset = DreamBoothSubset(
        **asdict(
            DreamBoothSubsetParams(
                image_dir=str(tmp_path),
                num_repeats=1,
                caption_extension=".txt",
                prefer_json_caption=True,
                cache_info=True,
            )
        )
    )

    dataset = DreamBoothDataset(
        subsets=[subset],
        is_training_dataset=True,
        batch_size=1,
        resolution=(8, 8),
        network_multiplier=1.0,
        enable_bucket=False,
        min_bucket_reso=256,
        max_bucket_reso=1024,
        bucket_reso_steps=64,
        bucket_no_upscale=False,
        prior_loss_weight=1.0,
        train_inpainting=False,
        debug_dataset=False,
        validation_split=0.0,
        validation_seed=None,
        resize_interpolation=None,
    )

    assert dataset.image_data[str(image_path)].caption == "character name, smile"
    cache = json.loads((tmp_path / "metadata_cache.json").read_text(encoding="utf-8"))
    assert cache[str(image_path)]["caption"] == "character name, smile"

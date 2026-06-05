import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mikazuki.utils import train_utils  # noqa: E402


def test_get_total_images_stops_at_limit(tmp_path):
    for index in range(250):
        (tmp_path / f"{index:03d}.png").write_bytes(b"")

    images = train_utils.get_total_images(str(tmp_path), limit=200)

    assert len(images) == 200


def test_get_total_images_with_limit_returns_empty_for_missing_path(tmp_path):
    images = train_utils.get_total_images(str(tmp_path / "missing"), limit=200)

    assert images == []


def test_get_total_images_with_limit_returns_empty_for_missing_non_recursive_path(tmp_path):
    images = train_utils.get_total_images(str(tmp_path / "missing"), recursive=False, limit=200)

    assert images == []

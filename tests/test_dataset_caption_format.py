from pathlib import Path

import pytest
from fastapi import HTTPException

from mikazuki.dataset_editor import caption_projection, detect_caption_format, scan_dataset


def test_caption_format_projection_distinguishes_tag_natural_and_mixed():
    assert detect_caption_format("1girl, solo, blue_hair") == "tag"
    assert detect_caption_format("一个女孩站在窗边，阳光从侧面照进来。") == "natural"
    format_name, tags, natural = caption_projection("1girl, solo\n\n一个女孩站在窗边。")
    assert format_name == "mixed"
    assert tags == ["1girl", "solo"]
    assert natural == "一个女孩站在窗边。"


def test_scan_dataset_does_not_expose_natural_text_as_tags(tmp_path: Path):
    image = tmp_path / "sample.png"
    image.write_bytes(b"not-an-image")
    image.with_suffix(".txt").write_text("一只猫坐在窗边，阳光很亮。", encoding="utf-8")
    result = scan_dataset(tmp_path)
    assert result["items"][0]["caption_format"] == "natural"
    assert result["items"][0]["tags"] == []
    assert result["items"][0]["natural_text"].startswith("一只猫")


def test_caption_first_mixed_projection_preserves_original_text():
    raw = "  女孩站在窗边。\n\n1girl, solo\n"
    kind, tags, natural = caption_projection(raw)
    assert kind == "mixed"
    assert tags == ["1girl", "solo"]
    assert natural == "女孩站在窗边。"


def test_raw_natural_caption_keeps_whitespace_on_save_and_reload(tmp_path):
    from mikazuki.dataset_editor import read_caption, write_caption
    image = tmp_path / "example.png"
    image.write_bytes(b"fake")
    raw = "  一个女孩站在窗边。\n\n这是第二段。\n"
    assert write_caption(image, raw) == raw
    assert read_caption(image) == raw

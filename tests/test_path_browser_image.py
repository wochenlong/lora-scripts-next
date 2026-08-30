from pathlib import Path

import pytest

from mikazuki.utils import path_browser


def test_resolve_image_path_accepts_image_files_and_rejects_non_images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    image = tmp_path / "preview.png"
    image.write_bytes(b"png")
    text = tmp_path / "notes.txt"
    text.write_text("notes", encoding="utf-8")

    assert path_browser.resolve_image_path(str(image)) == image.resolve()

    with pytest.raises(ValueError, match="图片"):
        path_browser.resolve_image_path(str(text))


def test_resolve_image_path_rejects_missing_and_denied_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError):
        path_browser.resolve_image_path(str(tmp_path / "missing.png"))

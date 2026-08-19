from __future__ import annotations

from pathlib import Path

import pytest

from mikazuki.utils import path_browser as pb


def test_list_directory_folder_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "train").mkdir()
    (tmp_path / "train" / "subset").mkdir()
    (tmp_path / "train" / "note.txt").write_text("x", encoding="utf-8")

    data = pb.list_directory(str(tmp_path / "train"), mode="folder")
    names = {e["name"] for e in data["entries"]}
    assert "subset" in names
    assert "note.txt" not in names
    assert data["path"].replace("\\", "/").endswith("/train")
    assert data["parent"] is not None


def test_list_directory_file_mode_filters_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    models = tmp_path / "sd-models"
    models.mkdir()
    (models / "a.safetensors").write_bytes(b"1")
    (models / "b.txt").write_text("nope", encoding="utf-8")
    (models / "nested").mkdir()

    data = pb.list_directory(str(models), mode="file", name_filter="*.safetensors;*.ckpt;*.pt")
    by_name = {e["name"]: e for e in data["entries"]}
    assert by_name["a.safetensors"]["type"] == "file"
    assert by_name["nested"]["type"] == "dir"
    assert "b.txt" not in by_name


def test_is_denied_linux_virtual_fs(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pb.sys, "platform", "linux")

    class FakePath:
        def resolve(self):
            return Path("/proc/self")

    assert pb._is_denied(FakePath())  # type: ignore[arg-type]


def test_default_roots_include_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sd-models").mkdir()
    roots = pb.default_roots()
    labels = {r["id"] for r in roots}
    assert "cwd" in labels
    assert "sd-models" in labels

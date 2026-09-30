"""Tests for the dataset TOML validator and /api/dataset/validate endpoint."""

from pathlib import Path

from fastapi.testclient import TestClient

from mikazuki.app.application import app
from mikazuki.utils.dataset_validate import validate_dataset_toml


def write_toml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "dataset.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_valid_kohya_toml_passes(tmp_path):
    image_dir = tmp_path / "imgs"
    image_dir.mkdir()
    path = write_toml(tmp_path, f"""
[general]
caption_extension = ".txt"
keep_tokens = 1

[[datasets]]
resolution = [1024, 1024]
batch_size = 1
enable_bucket = true

  [[datasets.subsets]]
  image_dir = "{image_dir}"
  num_repeats = 2
""")

    result = validate_dataset_toml(str(path))

    assert result["ok"] is True
    assert result["errors"] == []


def test_anima_fast_only_fields_are_rejected_with_hint(tmp_path):
    path = write_toml(tmp_path, """
[[datasets]]
resolution = 1024
validation_split_num = 4
recursive = true
cache_dir = "/tmp/cache"

  [[datasets.subsets]]
  image_dir = "/nonexistent-dir-for-test"
""")

    result = validate_dataset_toml(str(path))

    assert result["ok"] is False
    joined = "\n".join(result["errors"])
    assert "validation_split_num" in joined
    assert "recursive" in joined
    assert "cache_dir" in joined
    assert "image_dir 不存在" in joined


def test_missing_resolution_and_subsets(tmp_path):
    path = write_toml(tmp_path, "[[datasets]]\nbatch_size = 1\n")

    result = validate_dataset_toml(str(path))

    assert result["ok"] is False
    joined = "\n".join(result["errors"])
    assert "resolution" in joined
    assert "subsets" in joined


def test_missing_file_and_broken_toml(tmp_path):
    missing = validate_dataset_toml(str(tmp_path / "nope.toml"))
    assert missing["ok"] is False
    assert "不存在" in missing["errors"][0]

    broken = write_toml(tmp_path, "[[datasets]\n")
    result = validate_dataset_toml(str(broken))
    assert result["ok"] is False
    assert "TOML 解析失败" in result["errors"][0]


def test_relative_image_dir_resolves_against_toml_location(tmp_path):
    image_dir = tmp_path / "rel_imgs"
    image_dir.mkdir()
    path = write_toml(tmp_path, """
[[datasets]]
resolution = 512

  [[datasets.subsets]]
  image_dir = "rel_imgs"
""")

    result = validate_dataset_toml(str(path))

    assert result["ok"] is True


def test_validate_endpoint_roundtrip(tmp_path):
    image_dir = tmp_path / "imgs"
    image_dir.mkdir()
    path = write_toml(tmp_path, f"""
[[datasets]]
resolution = 512

  [[datasets.subsets]]
  image_dir = "{image_dir}"
""")

    client = TestClient(app)
    response = client.post("/api/dataset/validate", json={"path": str(path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["ok"] is True


def test_validate_endpoint_rejects_missing_path_field():
    client = TestClient(app)
    response = client.post("/api/dataset/validate", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "fail"

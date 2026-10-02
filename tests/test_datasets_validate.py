from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from mikazuki.app.application import app


def make_image(path: Path, color=(255, 0, 0)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color).save(path)


def validate(path: str, engine: str | None = None):
    client = TestClient(app)
    response = client.post("/api/datasets/validate", json={"path": path, "engine": engine})
    assert response.status_code == 200
    return response.json()["data"]


def codes(data):
    return [finding["code"] for finding in data["findings"]]


def test_empty_path_is_error():
    data = validate("   ")
    assert data["exists"] is False
    assert codes(data) == ["path-empty"]


def test_missing_path_is_error(tmp_path):
    data = validate(str(tmp_path / "nope"))
    assert data["exists"] is False
    assert codes(data) == ["path-missing"]


def test_file_path_is_not_directory(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    data = validate(str(target))
    assert data["exists"] is False
    assert codes(data) == ["not-directory"]


def test_directory_without_images_is_error(tmp_path):
    (tmp_path / "readme.txt").write_text("x", encoding="utf-8")
    data = validate(str(tmp_path))
    assert data["exists"] is True
    assert data["stats"]["image_count"] == 0
    assert "no-images" in codes(data)


def test_counts_images_and_captions(tmp_path):
    make_image(tmp_path / "a.png")
    make_image(tmp_path / "b.png")
    (tmp_path / "a.txt").write_text("tag", encoding="utf-8")

    data = validate(str(tmp_path))

    stats = data["stats"]
    assert stats["image_count"] == 2
    assert stats["captioned_count"] == 1
    assert stats["missing_caption"] == 1
    findings = {f["code"]: f for f in data["findings"]}
    assert findings["missing-captions"]["level"] == "warning"
    assert findings["missing-captions"]["params"] == {"missing": 1, "total": 2}


def test_nested_subdirs_reported_and_hidden_dirs_skipped(tmp_path):
    make_image(tmp_path / "10_concept" / "x.png")
    make_image(tmp_path / ".trash" / "batch" / "ghost.png")

    data = validate(str(tmp_path))

    assert data["stats"]["image_count"] == 1
    assert data["stats"]["subdir_count"] == 1
    assert "nested-images" in codes(data)


def test_unreadable_image_is_warning(tmp_path):
    (tmp_path / "broken.png").write_bytes(b"not an image")

    data = validate(str(tmp_path))

    findings = {f["code"]: f for f in data["findings"]}
    assert findings["unreadable-images"]["level"] == "warning"
    assert findings["unreadable-images"]["params"]["samples"] == ["broken.png"]


def test_kohya_engine_hints_repeats_convention(tmp_path):
    make_image(tmp_path / "plain" / "x.png")

    hinted = validate(str(tmp_path), engine="kohya")
    assert "kohya-subdir-convention" in codes(hinted)

    make_image(tmp_path / "5_style" / "y.png")
    conformed = validate(str(tmp_path), engine="kohya")
    assert "kohya-subdir-convention" not in codes(conformed)

    generic = validate(str(tmp_path), engine="unknown-engine")
    assert generic["engine"] is None
    assert "kohya-subdir-convention" not in codes(generic)


def test_validation_is_read_only(tmp_path):
    make_image(tmp_path / "sub" / "x.png")
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))

    validate(str(tmp_path), engine="kohya")

    after = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    assert before == after


def test_relative_path_resolves_against_repo_root(tmp_path, monkeypatch):
    make_image(tmp_path / "rel" / "x.png")
    monkeypatch.setattr("mikazuki.datasets.validate.resolve_root", lambda raw: (tmp_path / raw).resolve())

    data = validate("rel")

    assert data["exists"] is True
    assert data["stats"]["image_count"] == 1

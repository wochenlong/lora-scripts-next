from pathlib import Path

from fastapi.testclient import TestClient

from mikazuki.app.application import app
from mikazuki.app import api


def test_preview_image_serves_an_uploaded_cached_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    image = tmp_path / ".runtime" / "training-preview" / "selected.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    response = TestClient(app).get("/api/training/preview-image", params={"path": str(image)})

    assert response.status_code == 200
    assert response.content == image.read_bytes()


def test_preview_image_rejects_images_outside_the_upload_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    image = tmp_path / "secret.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    response = TestClient(app).get("/api/training/preview-image", params={"path": str(image)})

    assert response.status_code == 403


def test_preview_upload_rejects_oversized_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(api, "TRAINING_PREVIEW_MAX_BYTES", 4)

    response = TestClient(app).post(
        "/api/training/preview-upload",
        files={"file": ("large.png", b"12345", "image/png")},
    )

    assert response.status_code == 413
    assert not list((tmp_path / ".runtime" / "training-preview").glob("*"))


def test_preview_upload_prunes_old_cached_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(api, "TRAINING_PREVIEW_MAX_FILES", 2)
    target = tmp_path / ".runtime" / "training-preview"
    target.mkdir(parents=True)
    old = target / "old.png"
    recent = target / "recent.png"
    old.write_bytes(b"old")
    recent.write_bytes(b"recent")
    old.touch()
    recent.touch()
    old_stat = old.stat()
    recent_stat = recent.stat()
    old.touch()
    recent.touch()
    import os
    os.utime(old, (old_stat.st_atime, 1))
    os.utime(recent, (recent_stat.st_atime, 2))

    response = TestClient(app).post(
        "/api/training/preview-upload",
        files={"file": ("new.png", b"new", "image/png")},
    )

    assert response.status_code == 200
    assert not old.exists()
    assert recent.exists()
    assert len(list(target.glob("*"))) == 2

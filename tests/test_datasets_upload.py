import io
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mikazuki.app.application import app
from mikazuki.app.config import app_config
from mikazuki.datasets import upload as upload_module


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    dataset_dir = root / "ds"
    dataset_dir.mkdir(parents=True)
    monkeypatch.setitem(app_config._stored, "datasets_root", str(root))
    monkeypatch.setattr(app_config, "save_config", lambda: None)
    return dataset_dir


def png_bytes(color=(200, 100, 100)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 12), color).save(buffer, format="PNG")
    return buffer.getvalue()


def post_files(client: TestClient, name: str, files: list[tuple[str, bytes]], conflict: str | None = None):
    data = {"conflict": conflict} if conflict else {}
    return client.post(
        f"/api/datasets/{name}/upload",
        files=[("files", (filename, content)) for filename, content in files],
        data=data,
    )


def test_upload_images_and_captions_preserves_hierarchy(dataset):
    client = TestClient(app)
    response = post_files(client, "ds", [
        ("a.png", png_bytes()),
        ("sub/dir/b.jpg", png_bytes()),
        ("sub/dir/b.txt", "1girl, solo".encode()),
    ])

    assert response.status_code == 200
    data = response.json()["data"]
    assert sorted(data["succeeded"]) == ["a.png", "sub/dir/b.jpg", "sub/dir/b.txt"]
    assert data["skipped"] == []
    assert data["failed"] == []
    assert (dataset / "a.png").is_file()
    assert (dataset / "sub/dir/b.jpg").is_file()
    assert (dataset / "sub/dir/b.txt").read_text(encoding="utf-8") == "1girl, solo"
    assert not (dataset.parent / ".upload-tmp").exists() or not list((dataset.parent / ".upload-tmp").iterdir())


def test_upload_conflict_defaults_to_skip(dataset):
    (dataset / "a.png").write_bytes(b"original")

    client = TestClient(app)
    response = post_files(client, "ds", [("a.png", png_bytes())])

    data = response.json()["data"]
    assert data["skipped"] == ["a.png"]
    assert data["succeeded"] == []
    assert (dataset / "a.png").read_bytes() == b"original"


def test_upload_conflict_overwrite_replaces(dataset):
    (dataset / "a.png").write_bytes(b"original")

    client = TestClient(app)
    response = post_files(client, "ds", [("a.png", png_bytes())], conflict="overwrite")

    data = response.json()["data"]
    assert data["succeeded"] == ["a.png"]
    assert (dataset / "a.png").read_bytes() != b"original"


def test_upload_rejects_unsupported_type_and_bad_paths(dataset):
    client = TestClient(app)
    response = post_files(client, "ds", [
        ("evil.exe", b"x"),
        ("../escape.png", png_bytes()),
        (".hidden/secret.png", png_bytes()),
        ("ok.png", png_bytes()),
    ])

    data = response.json()["data"]
    assert data["succeeded"] == ["ok.png"]
    assert len(data["failed"]) == 3
    assert not (dataset / "evil.exe").exists()
    assert not (dataset.parent / "escape.png").exists()


def test_upload_rejects_unreadable_image(dataset):
    client = TestClient(app)
    response = post_files(client, "ds", [("broken.png", b"not an image")])

    data = response.json()["data"]
    assert data["succeeded"] == []
    assert data["failed"][0]["path"] == "broken.png"
    assert not (dataset / "broken.png").exists()


def test_upload_rejects_duplicate_path_in_batch(dataset):
    client = TestClient(app)
    response = post_files(client, "ds", [("a.png", png_bytes()), ("a.png", png_bytes())])

    data = response.json()["data"]
    assert data["succeeded"] == ["a.png"]
    assert data["failed"][0]["reason"] == "duplicate path in batch"


def test_upload_rejects_oversized_file(dataset, monkeypatch):
    monkeypatch.setattr(upload_module, "MAX_FILE_BYTES", 64)

    client = TestClient(app)
    response = post_files(client, "ds", [("big.png", b"x" * 128)])

    data = response.json()["data"]
    assert data["succeeded"] == []
    assert "limit" in data["failed"][0]["reason"]
    assert not (dataset / "big.png").exists()


def test_upload_missing_dataset_404(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    root.mkdir(parents=True)
    monkeypatch.setitem(app_config._stored, "datasets_root", str(root))
    monkeypatch.setattr(app_config, "save_config", lambda: None)

    client = TestClient(app)
    response = post_files(client, "ghost", [("a.png", png_bytes())])
    assert response.status_code == 404


def test_upload_requires_files(dataset):
    client = TestClient(app)
    response = client.post("/api/datasets/ds/upload", data={"conflict": "skip"})
    assert response.status_code == 400


def test_move_staged_no_overwrite_never_replaces(dataset):
    target = dataset / "a.png"
    target.write_bytes(b"original")
    staged = dataset.parent / "staged-a.png"
    staged.write_bytes(b"replacement")

    assert upload_module.move_staged(staged, target, overwrite=False) is False
    assert target.read_bytes() == b"original"
    assert not staged.exists()

    staged_b = dataset.parent / "staged-b.png"
    staged_b.write_bytes(b"fresh")
    assert upload_module.move_staged(staged_b, dataset / "b.png", overwrite=False) is True
    assert (dataset / "b.png").read_bytes() == b"fresh"


def test_ensure_capacity_does_not_double_count_staged_bytes(dataset, monkeypatch):
    staged = dataset.parent / "staged.bin"
    staged.write_bytes(b"x" * 4096)

    class Usage:
        free = 0

    monkeypatch.setattr(upload_module.shutil, "disk_usage", lambda _p: Usage())
    upload_module.ensure_capacity(dataset, [(staged, dataset / "bin")])


def test_upload_check_classifies_conflicts_and_invalid(dataset):
    (dataset / "sub").mkdir()
    (dataset / "exists.png").write_bytes(b"x")
    (dataset / "sub").joinpath("taken.txt").write_text("y", encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/datasets/ds/upload/check",
        json={"paths": ["exists.png", "sub/taken.txt", "new.png", "deep/nested/c.jpg", "bad.exe", "../escape.png"]},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert sorted(data["conflicts"]) == ["exists.png", "sub/taken.txt"]
    assert data["ok"] == 2
    assert len(data["invalid"]) == 2


def test_upload_check_missing_dataset_404(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    root.mkdir(parents=True)
    monkeypatch.setitem(app_config._stored, "datasets_root", str(root))
    monkeypatch.setattr(app_config, "save_config", lambda: None)

    client = TestClient(app)
    response = client.post("/api/datasets/ghost/upload/check", json={"paths": ["a.png"]})
    assert response.status_code == 404


def test_upload_rejects_bad_conflict_mode(dataset):
    client = TestClient(app)
    response = post_files(client, "ds", [("a.png", png_bytes())], conflict="rename")
    assert response.status_code == 400


def test_upload_enospc_during_staging_returns_507(dataset, monkeypatch):
    import errno as errno_module

    real_open = Path.open

    def fake_open(self, mode="r", *args, **kwargs):
        if ".upload-tmp" in str(self) and "w" in mode:
            raise OSError(errno_module.ENOSPC, "No space left on device")
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)
    (dataset / "keep.png").write_bytes(b"keep")

    client = TestClient(app, raise_server_exceptions=False)
    response = post_files(client, "ds", [("a.png", png_bytes())])

    assert response.status_code == 507
    assert (dataset / "keep.png").read_bytes() == b"keep"
    assert not (dataset / "a.png").exists()
    staging_root = dataset.parent / ".upload-tmp"
    assert not staging_root.exists() or not list(staging_root.iterdir())


def test_upload_low_disk_headroom_returns_507(dataset, monkeypatch):
    monkeypatch.setattr(
        upload_module.shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(10**12, 10**12 - 1, 1),
    )
    (dataset / "keep.png").write_bytes(b"keep")

    client = TestClient(app, raise_server_exceptions=False)
    response = post_files(client, "ds", [("a.png", png_bytes())])

    assert response.status_code == 507
    assert (dataset / "keep.png").read_bytes() == b"keep"
    assert not (dataset / "a.png").exists()
    staging_root = dataset.parent / ".upload-tmp"
    assert not staging_root.exists() or not list(staging_root.iterdir())

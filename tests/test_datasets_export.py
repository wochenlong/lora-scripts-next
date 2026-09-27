import asyncio
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mikazuki.app.application import app
from mikazuki.app.config import app_config


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    dataset_dir = root / "ds"
    nested = dataset_dir / "sub"
    nested.mkdir(parents=True)
    (dataset_dir / "a.png").write_bytes(b"png-a")
    (dataset_dir / "a.txt").write_text("1girl", encoding="utf-8")
    (nested / "b.jpg").write_bytes(b"jpg-b")
    (dataset_dir / ".hidden").mkdir()
    (dataset_dir / ".hidden" / "secret.png").write_bytes(b"nope")
    monkeypatch.setitem(app_config._stored, "datasets_root", str(root))
    monkeypatch.setattr(app_config, "save_config", lambda: None)
    return dataset_dir


def test_download_single_file(dataset):
    client = TestClient(app)
    response = client.get("/api/datasets/ds/file", params={"path": "sub/b.jpg"})

    assert response.status_code == 200
    assert response.content == b"jpg-b"
    assert "attachment" in response.headers["content-disposition"]


def test_download_single_file_rejects_escape_and_missing(dataset):
    client = TestClient(app)
    assert client.get("/api/datasets/ds/file", params={"path": "../outside"}).status_code in (400, 404)
    assert client.get("/api/datasets/ds/file", params={"path": "missing.png"}).status_code == 404


def test_download_dataset_zip_streams_hierarchy_without_hidden(dataset):
    client = TestClient(app)
    response = client.get("/api/datasets/ds/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "ds.zip" in response.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = sorted(archive.namelist())
        assert names == ["a.png", "a.txt", "sub/b.jpg"]
        assert archive.read("a.txt").decode() == "1girl"


def test_download_missing_dataset_404(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    root.mkdir(parents=True)
    monkeypatch.setitem(app_config._stored, "datasets_root", str(root))
    monkeypatch.setattr(app_config, "save_config", lambda: None)

    client = TestClient(app)
    assert client.get("/api/datasets/ghost/download").status_code == 404


def test_zip_export_skips_symlinked_files(dataset):
    outside = dataset.parent / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("topsecret", encoding="utf-8")
    (dataset / "link.txt").symlink_to(outside / "secret.txt")

    client = TestClient(app)
    response = client.get("/api/datasets/ds/download")

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "link.txt" not in archive.namelist()
    assert b"topsecret" not in response.content


def test_zip_export_skips_symlinked_directories(dataset):
    outside = dataset.parent / "outside-dir"
    outside.mkdir()
    (outside / "leak.png").write_bytes(b"leak")
    (dataset / "linked").symlink_to(outside, target_is_directory=True)

    client = TestClient(app)
    response = client.get("/api/datasets/ds/download")

    assert response.status_code == 200
    assert b"leak" not in response.content


def test_zip_export_worker_error_is_visible(dataset, monkeypatch):
    from mikazuki.datasets import export as export_module

    def boom(_dir):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    monkeypatch.setattr(export_module, "iter_exportable_files", boom)
    response = export_module.stream_dataset_zip(dataset)

    async def drain():
        async for _ in response.body_iterator:
            pass

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(drain())


def test_queue_writer_unblocks_after_cancel():
    from mikazuki.datasets.export import _QueueWriter

    writer = _QueueWriter(maxsize=1)
    writer.write(b"a")
    writer.cancelled = True
    with pytest.raises(OSError):
        writer.write(b"b")

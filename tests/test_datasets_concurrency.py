import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mikazuki.app.application import app
from mikazuki.app.config import app_config
from mikazuki.datasets import locks
from mikazuki.datasets.locks import lock_for


@pytest.fixture(autouse=True)
def fast_lock_timeout(monkeypatch):
    monkeypatch.setattr(locks, "ACQUIRE_TIMEOUT_SECONDS", 0.05)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    dataset_dir = root / "ds"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "a.png").write_bytes(b"png-a")
    (dataset_dir / "a.txt").write_text("1girl", encoding="utf-8")
    monkeypatch.setitem(app_config._stored, "datasets_root", str(root))
    monkeypatch.setattr(app_config, "save_config", lambda: None)
    return root, dataset_dir


def test_writes_rejected_while_dataset_operation_holds_lock(workspace):
    _root, _dataset_dir = workspace
    client = TestClient(app)
    lock = lock_for("ds")
    assert lock.acquire(blocking=False)
    try:
        upload = client.post(
            "/api/datasets/ds/upload",
            files=[("files", ("b.png", io.BytesIO(b"png-b"), "image/png"))],
        )
        assert upload.status_code == 409

        assert client.request("DELETE", "/api/datasets/ds/files", json={"paths": ["a.png"]}).status_code == 409
        assert client.delete("/api/datasets/ds").status_code == 409
        assert client.post("/api/datasets/ds/trash/restore", json={"id": "x"}).status_code == 409
        assert client.post("/api/datasets/ds/trash/empty", json={"confirm": True}).status_code == 409
        assert client.post("/api/datasets", json={"name": "ds"}).status_code == 409
    finally:
        lock.release()

    after = client.post(
        "/api/datasets/ds/upload",
        files=[("files", ("b.png", io.BytesIO(b"png-b"), "image/png"))],
    )
    assert after.status_code == 200


def test_other_dataset_not_blocked_by_lock(workspace):
    root, _dataset_dir = workspace
    other = root / "other"
    other.mkdir()
    (other / "x.png").write_bytes(b"x")
    client = TestClient(app)
    lock = lock_for("ds")
    assert lock.acquire(blocking=False)
    try:
        response = client.request("DELETE", "/api/datasets/other/files", json={"paths": ["x.png"]})
        assert response.status_code == 200
    finally:
        lock.release()


def test_global_restore_rejected_while_dataset_locked(workspace):
    root, _dataset_dir = workspace
    client = TestClient(app)
    batch = client.delete("/api/datasets/ds").json()["data"]["batch"]

    lock = lock_for("ds")
    assert lock.acquire(blocking=False)
    try:
        response = client.post("/api/datasets-trash/restore", json={"id": batch})
        assert response.status_code == 409
        assert (root / ".trash" / batch / "files" / "a.png").is_file()
    finally:
        lock.release()

    result = client.post("/api/datasets-trash/restore", json={"id": batch}).json()["data"]
    assert sorted(result["restored"]) == ["a.png", "a.txt"]


def test_upload_deleted_dataset_during_staging_returns_409(workspace, monkeypatch):
    root, dataset_dir = workspace
    client = TestClient(app)

    import mikazuki.datasets.api as api_module

    original = api_module.dataset_operation

    class deleting_operation:
        def __init__(self, name):
            self.inner = original(name)

        def __enter__(self):
            import shutil

            shutil.rmtree(dataset_dir)
            return self.inner.__enter__()

        def __exit__(self, *exc):
            return self.inner.__exit__(*exc)

    monkeypatch.setattr(api_module, "dataset_operation", deleting_operation)
    response = client.post(
        "/api/datasets/ds/upload",
        files=[("files", ("b.png", io.BytesIO(b"png-b"), "image/png"))],
    )
    assert response.status_code == 409
    assert not dataset_dir.exists()
    assert not list((root / ".upload-tmp").iterdir()) if (root / ".upload-tmp").exists() else True

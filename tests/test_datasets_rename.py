from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mikazuki.app.application import app
from mikazuki.app.config import app_config
from mikazuki.datasets import in_use
from mikazuki.tasks import Task, TaskStatus, tm


@pytest.fixture
def datasets_root(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    monkeypatch.setitem(app_config._stored, "datasets_root", str(root))
    monkeypatch.setattr(app_config, "save_config", lambda: None)
    monkeypatch.setattr(tm, "tasks", {})
    in_use.invalidate_in_use_cache()
    yield root
    in_use.invalidate_in_use_cache()


def make_dataset(root: Path, name: str) -> Path:
    dataset_dir = root / name
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "a.png").write_bytes(b"png")
    (dataset_dir / "a.txt").write_text("caption", encoding="utf-8")
    return dataset_dir


def test_rename_moves_directory(datasets_root):
    make_dataset(datasets_root, "old")

    client = TestClient(app)
    response = client.post("/api/datasets/old/rename", json={"new_name": "new"})

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "new"
    assert not (datasets_root / "old").exists()
    assert (datasets_root / "new" / "a.png").is_file()


def test_rename_rejects_existing_name(datasets_root):
    make_dataset(datasets_root, "old")
    make_dataset(datasets_root, "new")

    client = TestClient(app)
    assert client.post("/api/datasets/old/rename", json={"new_name": "new"}).status_code == 409
    assert (datasets_root / "old" / "a.png").is_file()


def test_rename_rejects_missing_source(datasets_root):
    datasets_root.mkdir(parents=True)

    client = TestClient(app)
    assert client.post("/api/datasets/gone/rename", json={"new_name": "new"}).status_code == 404


def test_rename_rejects_invalid_name(datasets_root):
    make_dataset(datasets_root, "old")

    client = TestClient(app)
    assert client.post("/api/datasets/old/rename", json={"new_name": "../escape"}).status_code == 400


def test_rename_rejected_while_in_use(datasets_root, tmp_path):
    make_dataset(datasets_root, "busy")
    config = tmp_path / "conf.toml"
    config.write_text(f'train_data_dir = "{(datasets_root / "busy").as_posix()}"\n', encoding="utf-8")
    task = Task("lock-busy", ["true"], metadata={"config_path": str(config.resolve()), "cwd": str(tmp_path)})
    task.status = TaskStatus.QUEUED
    tm.tasks[task.task_id] = task
    in_use.invalidate_in_use_cache()

    client = TestClient(app)
    assert client.post("/api/datasets/busy/rename", json={"new_name": "new"}).status_code == 409
    assert (datasets_root / "busy" / "a.png").is_file()


def test_rename_retargets_trash_batches(datasets_root):
    dataset_dir = make_dataset(datasets_root, "old")

    client = TestClient(app)
    delete = client.request("DELETE", "/api/datasets/old/files", json={"paths": ["a.png"]})
    assert delete.status_code == 200
    batch_id = delete.json()["data"]["batch"]

    response = client.post("/api/datasets/old/rename", json={"new_name": "new"})
    assert response.status_code == 200

    old_trash = client.get("/api/datasets/new/trash")
    assert [batch["id"] for batch in old_trash.json()["data"]["batches"]] == [batch_id]

    restore = client.post("/api/datasets/new/trash/restore", json={"id": batch_id})
    assert restore.status_code == 200
    assert (datasets_root / "new" / "a.png").is_file()
    assert not (datasets_root / "old").exists()
    assert dataset_dir.name == "old"

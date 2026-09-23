import io
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


def lock_dataset(root: Path, name: str, tmp_path: Path) -> Task:
    config = tmp_path / f"{name}.toml"
    config.write_text(f'train_data_dir = "{(root / name).as_posix()}"\n', encoding="utf-8")
    task = Task(f"lock-{name}", ["true"], metadata={"config_path": str(config.resolve()), "job_label": "Training", "cwd": str(tmp_path)})
    task.status = TaskStatus.QUEUED
    tm.tasks[task.task_id] = task
    in_use.invalidate_in_use_cache()
    return task


def make_dataset(root: Path, name: str) -> Path:
    dataset_dir = root / name
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "a.png").write_bytes(b"png")
    return dataset_dir


def test_list_reports_in_use_tasks(datasets_root, tmp_path):
    make_dataset(datasets_root, "busy")
    make_dataset(datasets_root, "idle")
    task = lock_dataset(datasets_root, "busy", tmp_path)

    client = TestClient(app)
    response = client.get("/api/datasets")

    assert response.status_code == 200
    entries = {item["name"]: item for item in response.json()["data"]["datasets"]}
    assert entries["busy"]["in_use"] == [{"task_id": task.task_id, "job_label": "Training"}]
    assert entries["idle"]["in_use"] == []


def test_mutations_rejected_with_409_while_in_use(datasets_root, tmp_path):
    make_dataset(datasets_root, "busy")
    lock_dataset(datasets_root, "busy", tmp_path)

    client = TestClient(app)
    assert client.delete("/api/datasets/busy").status_code == 409
    assert client.request("DELETE", "/api/datasets/busy/files", json={"paths": ["a.png"]}).status_code == 409
    assert client.post("/api/datasets/busy/trash/restore", json={"id": "whatever"}).status_code == 409
    assert client.post("/api/datasets/busy/trash/empty", json={"confirm": True}).status_code == 409
    upload = client.post("/api/datasets/busy/upload", files={"files": ("b.png", io.BytesIO(b"png"), "image/png")})
    assert upload.status_code == 409


def test_read_only_endpoints_still_work_while_in_use(datasets_root, tmp_path):
    make_dataset(datasets_root, "busy")
    lock_dataset(datasets_root, "busy", tmp_path)

    client = TestClient(app)
    assert client.get("/api/datasets/busy/overview").status_code == 200
    assert client.get("/api/datasets/busy/file", params={"path": "a.png"}).status_code == 200
    assert client.get("/api/datasets/busy/download").status_code == 200


def test_mutations_allowed_after_task_finishes(datasets_root, tmp_path):
    dataset_dir = make_dataset(datasets_root, "busy")
    task = lock_dataset(datasets_root, "busy", tmp_path)

    task.status = TaskStatus.FINISHED
    in_use.invalidate_in_use_cache()

    client = TestClient(app)
    response = client.delete("/api/datasets/busy")
    assert response.status_code == 200
    assert not dataset_dir.exists()

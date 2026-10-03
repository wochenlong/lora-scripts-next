from pathlib import Path

import pytest
import toml
from fastapi.testclient import TestClient

from mikazuki.app.application import app
from mikazuki.app.config import app_config
from mikazuki.tasks import TaskStatus, tm


@pytest.fixture
def datasets_root(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    monkeypatch.setitem(app_config._stored, "datasets_root", str(root))
    monkeypatch.setattr(app_config, "save_config", lambda: None)
    return root


@pytest.fixture
def training_task(datasets_root, tmp_path):
    config = tmp_path / "task.toml"
    config.write_text(toml.dumps({"train_data_dir": str(datasets_root / "busy")}), encoding="utf-8")
    task = tm.create_task(["true"], None, metadata={"config_path": str(config)})
    task.status = TaskStatus.RUNNING
    yield task
    with tm._cond:
        tm.tasks.pop(task.task_id, None)


def make_dataset(root: Path, name: str) -> Path:
    dataset_dir = root / name
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "a.png").write_bytes(b"png")
    (dataset_dir / "a.txt").write_text("1girl", encoding="utf-8")
    return dataset_dir


def test_editor_caption_write_blocked_for_in_use_dataset(datasets_root, training_task):
    dataset_dir = make_dataset(datasets_root, "busy")
    client = TestClient(app)
    response = client.post("/api/dataset-editor/caption", json={
        "root": str(dataset_dir), "image": "a.png", "caption": "solo",
    })
    assert response.status_code == 409
    assert (dataset_dir / "a.txt").read_text(encoding="utf-8") == "1girl"


def test_editor_batch_and_undo_blocked_for_in_use_dataset(datasets_root, training_task):
    dataset_dir = make_dataset(datasets_root, "busy")
    client = TestClient(app)
    batch = client.post("/api/dataset-editor/batch", json={
        "root": str(dataset_dir), "images": ["a.png"], "append": [], "remove": ["1girl"], "replace": [],
    })
    assert batch.status_code == 409
    undo = client.post("/api/dataset-editor/undo", json={"root": str(dataset_dir)})
    assert undo.status_code == 409


def test_editor_writes_allowed_for_idle_dataset(datasets_root, training_task):
    dataset_dir = make_dataset(datasets_root, "idle")
    client = TestClient(app)
    response = client.post("/api/dataset-editor/caption", json={
        "root": str(dataset_dir), "image": "a.png", "caption": "solo",
    })
    assert response.status_code == 200
    assert (dataset_dir / "a.txt").read_text(encoding="utf-8") == "solo"


def test_editor_writes_allowed_outside_managed_root(datasets_root, training_task, tmp_path):
    outside = tmp_path / "external"
    outside.mkdir()
    (outside / "a.png").write_bytes(b"png")
    client = TestClient(app)
    response = client.post("/api/dataset-editor/caption", json={
        "root": str(outside), "image": "a.png", "caption": "solo",
    })
    assert response.status_code == 200


def test_interrogate_blocked_for_in_use_dataset(datasets_root, training_task):
    dataset_dir = make_dataset(datasets_root, "busy")
    client = TestClient(app)
    response = client.post("/api/interrogate", json={
        "path": str(dataset_dir), "interrogator_model": "wd14-convnextv2-v2",
    })
    assert response.json()["status"] == "fail"
    assert "锁定" in (response.json()["message"] or "")


def test_interrogate_allowed_for_idle_dataset(datasets_root, training_task, monkeypatch):
    dataset_dir = make_dataset(datasets_root, "idle")
    monkeypatch.setattr("mikazuki.app.api.run_interrogate_job", lambda req: None)
    client = TestClient(app)
    response = client.post("/api/interrogate", json={
        "path": str(dataset_dir), "interrogator_model": "wd14-convnextv2-v2",
    })
    assert response.json()["status"] == "success"

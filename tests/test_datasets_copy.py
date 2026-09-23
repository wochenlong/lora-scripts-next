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
    (dataset_dir / "sub").mkdir(parents=True)
    (dataset_dir / "a.png").write_bytes(b"png-a")
    (dataset_dir / "a.txt").write_text("caption", encoding="utf-8")
    (dataset_dir / "sub" / "b.png").write_bytes(b"png-b")
    return dataset_dir


def test_copy_duplicates_content_independently(datasets_root):
    source = make_dataset(datasets_root, "src")

    client = TestClient(app)
    response = client.post("/api/datasets/src/copy", json={"new_name": "dst"})

    assert response.status_code == 200
    target = datasets_root / "dst"
    assert (target / "a.png").read_bytes() == b"png-a"
    assert (target / "a.txt").read_text(encoding="utf-8") == "caption"
    assert (target / "sub" / "b.png").read_bytes() == b"png-b"

    (target / "a.txt").write_text("changed", encoding="utf-8")
    assert (source / "a.txt").read_text(encoding="utf-8") == "caption"


def test_copy_cleans_up_staging(datasets_root):
    make_dataset(datasets_root, "src")

    client = TestClient(app)
    assert client.post("/api/datasets/src/copy", json={"new_name": "dst"}).status_code == 200

    staging_root = datasets_root / ".copy-tmp"
    assert not staging_root.exists() or not list(staging_root.iterdir())


def test_copy_rejects_existing_name(datasets_root):
    make_dataset(datasets_root, "src")
    make_dataset(datasets_root, "dst")

    client = TestClient(app)
    assert client.post("/api/datasets/src/copy", json={"new_name": "dst"}).status_code == 409


def test_copy_rejects_missing_source(datasets_root):
    datasets_root.mkdir(parents=True)

    client = TestClient(app)
    assert client.post("/api/datasets/gone/copy", json={"new_name": "dst"}).status_code == 404


def test_copy_rejects_invalid_name(datasets_root):
    make_dataset(datasets_root, "src")

    client = TestClient(app)
    assert client.post("/api/datasets/src/copy", json={"new_name": "../escape"}).status_code == 400


def test_copy_allowed_while_source_in_use(datasets_root, tmp_path):
    make_dataset(datasets_root, "busy")
    config = tmp_path / "conf.toml"
    config.write_text(f'train_data_dir = "{(datasets_root / "busy").as_posix()}"\n', encoding="utf-8")
    task = Task("lock-busy", ["true"], metadata={"config_path": str(config.resolve()), "cwd": str(tmp_path)})
    task.status = TaskStatus.RUNNING
    tm.tasks[task.task_id] = task
    in_use.invalidate_in_use_cache()

    client = TestClient(app)
    response = client.post("/api/datasets/busy/copy", json={"new_name": "busy-v2"})

    assert response.status_code == 200
    assert (datasets_root / "busy-v2" / "a.png").is_file()

from pathlib import Path

import pytest
import toml
from fastapi.testclient import TestClient
from PIL import Image

from mikazuki.app.application import app
from mikazuki.app.config import app_config
from mikazuki.datasets.inuse import datasets_in_use
from mikazuki.tasks import TaskStatus, tm


@pytest.fixture
def datasets_root(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    monkeypatch.setitem(app_config._stored, "datasets_root", str(root))
    monkeypatch.setattr(app_config, "save_config", lambda: None)
    return root


def make_image(path: Path, mode="RGB", color=(255, 0, 0, 128)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, (8, 8), color).save(path)


def make_dataset(root: Path, name: str) -> Path:
    dataset_dir = root / name
    make_image(dataset_dir / "a.png", mode="RGBA")
    make_image(dataset_dir / "sub" / "b.png", mode="RGB", color=(0, 255, 0))
    (dataset_dir / "a.txt").write_text("1girl", encoding="utf-8")
    return dataset_dir


def test_copy_preserves_hierarchy_without_flatten(datasets_root):
    make_dataset(datasets_root, "src")
    client = TestClient(app)
    response = client.post("/api/datasets/src/copy", json={"name": "dst"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["copied"] == 3
    assert data["flattened"] == 0
    target = datasets_root / "dst"
    assert (target / "a.png").is_file()
    assert (target / "sub" / "b.png").is_file()
    assert (target / "a.txt").is_file()
    with Image.open(target / "a.png") as image:
        assert image.mode == "RGBA"


def test_copy_with_flatten_turns_transparency_white(datasets_root):
    make_dataset(datasets_root, "src")
    client = TestClient(app)
    response = client.post("/api/datasets/src/copy", json={"name": "flat", "flatten_transparent": True})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["copied"] == 3
    assert data["flattened"] == 1

    with Image.open(datasets_root / "flat" / "a.png") as image:
        assert image.mode == "RGB"
        assert image.size == (8, 8)
        assert image.convert("RGBA").getpixel((0, 0)) == (255, 127, 127, 255)
    with Image.open(datasets_root / "flat" / "sub" / "b.png") as image:
        assert image.mode == "RGB"


def test_copy_rejects_existing_target(datasets_root):
    make_dataset(datasets_root, "src")
    make_dataset(datasets_root, "dst")
    client = TestClient(app)
    assert client.post("/api/datasets/src/copy", json={"name": "dst"}).status_code == 409


def test_copy_missing_source_is_404(datasets_root):
    datasets_root.mkdir(parents=True)
    client = TestClient(app)
    assert client.post("/api/datasets/nope/copy", json={"name": "dst"}).status_code == 404


def test_copy_flatten_layout_drops_hierarchy(datasets_root):
    make_dataset(datasets_root, "src")
    client = TestClient(app)
    response = client.post("/api/datasets/src/copy", json={"name": "flat-layout", "layout": "flatten"})

    assert response.status_code == 200
    target = datasets_root / "flat-layout"
    assert (target / "a.png").is_file()
    assert (target / "b.png").is_file()
    assert not (target / "sub").exists()


def test_copy_flatten_dedupes_name_collisions(datasets_root):
    dataset_dir = datasets_root / "src"
    make_image(dataset_dir / "x" / "same.png", mode="RGB", color=(1, 2, 3))
    make_image(dataset_dir / "y" / "same.png", mode="RGB", color=(4, 5, 6))
    (dataset_dir / "x" / "same.txt").write_text("caption-x", encoding="utf-8")
    (dataset_dir / "y" / "same.txt").write_text("caption-y", encoding="utf-8")

    client = TestClient(app)
    response = client.post("/api/datasets/src/copy", json={"name": "dedup", "layout": "flatten"})

    assert response.status_code == 200
    assert response.json()["data"]["deduped"] >= 2
    target = datasets_root / "dedup"
    captions = sorted(p.read_text(encoding="utf-8") for p in target.glob("*.txt"))
    assert captions == ["caption-x", "caption-y"]
    # 每个 caption 仍与同 stem 的图片配对
    for caption in target.glob("*.txt"):
        assert caption.with_suffix(".png").is_file()


def test_copy_kohya_layout_wraps_subsets(datasets_root):
    make_dataset(datasets_root, "src")
    make_image(datasets_root / "src" / "5_kept" / "c.png", mode="RGB", color=(9, 9, 9))

    client = TestClient(app)
    response = client.post("/api/datasets/src/copy", json={"name": "kohya-ds", "layout": "kohya", "repeats": 7})

    assert response.status_code == 200
    target = datasets_root / "kohya-ds"
    assert (target / "7_kohya-ds" / "a.png").is_file()
    assert (target / "7_kohya-ds" / "a.txt").is_file()
    assert (target / "7_sub" / "b.png").is_file()
    # 已符合 N_ 约定的子目录原样保留
    assert (target / "5_kept" / "c.png").is_file()


def test_copy_rejects_bad_layout_and_repeats(datasets_root):
    make_dataset(datasets_root, "src")
    client = TestClient(app)
    assert client.post("/api/datasets/src/copy", json={"name": "x", "layout": "weird"}).status_code == 400
    assert client.post("/api/datasets/src/copy", json={"name": "x", "repeats": 0}).status_code == 400


@pytest.fixture
def training_task(datasets_root, tmp_path):
    config = tmp_path / "task.toml"
    config.write_text(toml.dumps({"train_data_dir": str(datasets_root / "src")}), encoding="utf-8")
    task = tm.create_task(["true"], None, metadata={"config_path": str(config)})
    task.status = TaskStatus.RUNNING
    yield task
    with tm._cond:
        tm.tasks.pop(task.task_id, None)


def test_in_use_detection_and_list_flag(datasets_root, training_task):
    make_dataset(datasets_root, "src")
    make_dataset(datasets_root, "idle")

    assert datasets_in_use() == {"src"}

    client = TestClient(app)
    entries = {d["name"]: d for d in client.get("/api/datasets").json()["data"]["datasets"]}
    assert entries["src"]["in_use"] is True
    assert entries["idle"]["in_use"] is False


def test_writes_rejected_while_training(datasets_root, training_task):
    make_dataset(datasets_root, "src")
    client = TestClient(app)

    response = client.request("DELETE", "/api/datasets/src/files", json={"paths": ["a.png"]})
    assert response.status_code == 409
    assert client.delete("/api/datasets/src").status_code == 409

    (datasets_root / "idle").mkdir()
    assert client.delete("/api/datasets/idle").status_code == 200


def test_finished_task_releases_dataset(datasets_root, training_task):
    make_dataset(datasets_root, "src")
    training_task.status = TaskStatus.FINISHED
    assert datasets_in_use() == set()

    client = TestClient(app)
    assert client.delete("/api/datasets/src").status_code == 200

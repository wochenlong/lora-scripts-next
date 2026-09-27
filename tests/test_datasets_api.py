from pathlib import Path

import time

import pytest
from fastapi.testclient import TestClient

from mikazuki.app.application import app
from mikazuki.app.config import app_config
from mikazuki.datasets import root as root_module
from mikazuki.datasets.stats import compute_overview


@pytest.fixture
def datasets_root(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    monkeypatch.setitem(app_config._stored, "datasets_root", str(root))
    monkeypatch.setattr(app_config, "save_config", lambda: None)
    return root


def make_dataset(root: Path, name: str):
    dataset_dir = root / name
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "alpha.png").write_bytes(b"png")
    return dataset_dir


def test_default_root_resolves_against_repo_root(monkeypatch):
    monkeypatch.delitem(app_config._stored, "datasets_root", raising=False)
    assert root_module.get_datasets_root() == (root_module.REPO_ROOT / "datasets").resolve()


def test_relative_root_resolves_against_repo_root_not_cwd(monkeypatch, tmp_path):
    monkeypatch.setitem(app_config._stored, "datasets_root", "./my-datasets")
    monkeypatch.chdir(tmp_path)
    assert root_module.get_datasets_root() == (root_module.REPO_ROOT / "my-datasets").resolve()


def test_get_root_reports_configured_path(datasets_root):
    client = TestClient(app)
    response = client.get("/api/datasets/root")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["root"] == str(datasets_root.resolve()).replace("\\", "/")
    assert data["default"] == "./datasets"
    assert data["exists"] is False


def test_update_root_creates_directory_without_touching_old_data(datasets_root, tmp_path):
    old_dir = make_dataset(tmp_path / "old-root", "keep-me")
    new_root = tmp_path / "new-root"

    client = TestClient(app)
    response = client.put("/api/datasets/root", json={"path": str(new_root)})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["root"] == str(new_root.resolve()).replace("\\", "/")
    assert data["exists"] is True
    assert new_root.is_dir()
    assert (old_dir / "alpha.png").is_file()
    assert app_config["datasets_root"] == str(new_root)


def test_update_root_rejects_empty_path(datasets_root):
    client = TestClient(app)
    response = client.put("/api/datasets/root", json={"path": "   "})
    assert response.status_code == 400


def test_list_datasets_discovers_first_level_dirs(datasets_root):
    make_dataset(datasets_root, "beta")
    make_dataset(datasets_root, "Alpha")
    (datasets_root / ".trash").mkdir(parents=True)
    (datasets_root / "loose-file.txt").write_text("x", encoding="utf-8")

    client = TestClient(app)
    response = client.get("/api/datasets")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["exists"] is True
    assert [d["name"] for d in data["datasets"]] == ["Alpha", "beta"]
    assert all("\\" not in d["path"] for d in data["datasets"])


def test_list_datasets_missing_root_returns_empty(datasets_root):
    client = TestClient(app)
    response = client.get("/api/datasets")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["exists"] is False
    assert data["datasets"] == []


def test_list_datasets_excludes_symlinked_directories(datasets_root, tmp_path):
    make_dataset(datasets_root, "real")
    outside = tmp_path / "outside"
    outside.mkdir()
    (datasets_root / "linked").symlink_to(outside, target_is_directory=True)

    client = TestClient(app)
    data = client.get("/api/datasets").json()["data"]
    assert [d["name"] for d in data["datasets"]] == ["real"]


def test_create_dataset(datasets_root):
    client = TestClient(app)
    response = client.post("/api/datasets", json={"name": "my-dataset"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "my-dataset"
    assert (datasets_root / "my-dataset").is_dir()


def test_create_dataset_conflict(datasets_root):
    make_dataset(datasets_root, "dup")

    client = TestClient(app)
    response = client.post("/api/datasets", json={"name": "dup"})
    assert response.status_code == 409


@pytest.mark.parametrize("name", ["../escape", "a/b", ".hidden", "", "  "])
def test_create_dataset_rejects_invalid_names(datasets_root, name):
    client = TestClient(app)
    response = client.post("/api/datasets", json={"name": name})
    assert response.status_code == 400


def poll_overview(client: TestClient, name: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while True:
        response = client.get(f"/api/datasets/{name}/overview")
        assert response.status_code == 200
        overview = response.json()["data"]["overview"]
        if overview["state"] != "computing" or time.time() > deadline:
            return overview
        time.sleep(0.05)


def test_compute_overview_counts_images_captions_and_bytes(tmp_path):
    dataset_dir = tmp_path / "ds"
    nested = dataset_dir / "subdir"
    nested.mkdir(parents=True)
    (dataset_dir / "a.png").write_bytes(b"x" * 10)
    (dataset_dir / "a.txt").write_text("1girl", encoding="utf-8")
    (nested / "b.jpg").write_bytes(b"y" * 20)

    overview = compute_overview(dataset_dir)

    assert overview["state"] == "ready"
    assert overview["file_count"] == 2
    assert overview["captioned_count"] == 1
    assert overview["total_bytes"] == 10 + 5 + 20
    assert overview["updated_at"] is not None


def test_overview_endpoint_is_async_and_eventually_ready(datasets_root):
    make_dataset(datasets_root, "stats-ds")

    client = TestClient(app)
    first = client.get("/api/datasets/stats-ds/overview")
    assert first.status_code == 200
    assert first.json()["data"]["overview"]["state"] in ("computing", "ready")

    overview = poll_overview(client, "stats-ds")
    assert overview["state"] == "ready"
    assert overview["file_count"] == 1
    assert overview["captioned_count"] == 0
    assert overview["total_bytes"] > 0


def test_overview_endpoint_missing_dataset(datasets_root):
    datasets_root.mkdir(parents=True)
    client = TestClient(app)
    assert client.get("/api/datasets/nope/overview").status_code == 404


def test_resolve_dataset_dir_rejects_symlink_escape(datasets_root, tmp_path):
    from fastapi import HTTPException

    from mikazuki.datasets.sandbox import resolve_dataset_dir

    datasets_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (datasets_root / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(HTTPException) as exc_info:
        resolve_dataset_dir(datasets_root.resolve(), "link")
    assert exc_info.value.status_code == 400


def test_list_datasets_embeds_cached_overview_without_blocking(datasets_root):
    make_dataset(datasets_root, "cached-ds")

    client = TestClient(app)
    first_list = client.get("/api/datasets").json()["data"]["datasets"]
    assert first_list[0]["name"] == "cached-ds"
    assert first_list[0]["overview"] is None

    overview = poll_overview(client, "cached-ds")
    assert overview["state"] == "ready"

    second_list = client.get("/api/datasets").json()["data"]["datasets"]
    cached = second_list[0]["overview"]
    assert cached["state"] == "ready"
    assert cached["file_count"] == 1

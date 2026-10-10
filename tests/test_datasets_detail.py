import os
import subprocess
import threading

import pytest
from fastapi.testclient import TestClient

from mikazuki.app.application import app
from mikazuki.app.config import app_config
from mikazuki.datasets import locks, stats
from mikazuki.datasets.root import normalize_path
from mikazuki.tasks import tm


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    source = root / "source"
    (source / "sub").mkdir(parents=True)
    (source / "a.PNG").write_bytes(b"image")
    (source / "a.txt").write_text("caption", encoding="utf-8")
    (source / "sub" / "nested.jpg").write_bytes(b"nested")
    (source / ".upload-tmp").mkdir()
    monkeypatch.setitem(app_config._stored, "datasets_root", str(root))
    monkeypatch.setattr(tm, "dump", lambda: [])
    monkeypatch.setattr(locks, "ACQUIRE_TIMEOUT_SECONDS", 0.05)
    return root, source, TestClient(app)


def test_rename_preserves_contents_and_invalidates_both_caches(workspace):
    root, source, client = workspace
    target = root / "renamed"
    for path in (source, target):
        stats._entries[normalize_path(path)] = {"state": "ready"}
    response = client.post("/api/datasets/source/rename", json={"name": " renamed "})
    assert response.status_code == 200
    assert response.json()["data"] == {"name": "renamed", "path": normalize_path(target)}
    assert not source.exists()
    assert (target / "a.txt").read_text(encoding="utf-8") == "caption"
    assert (target / "sub" / "nested.jpg").read_bytes() == b"nested"
    assert stats.cached_overview(source) is None
    assert stats.cached_overview(target) is None


@pytest.mark.parametrize("name", ["", " ", ".", "..", ".trash", "../escape", r"a\b", "a/b", "C:escape", "bad\x00name", "source.", "NUL", "bad?name"])
def test_rename_rejects_invalid_target(workspace, name):
    _, source, client = workspace
    assert client.post("/api/datasets/source/rename", json={"name": name}).status_code == 400
    assert source.is_dir()


@pytest.mark.parametrize("target", ["source", "existing", "existing-file"])
def test_rename_rejects_existing_target(workspace, target):
    root, source, client = workspace
    (root / "existing").mkdir()
    (root / "existing-file").write_bytes(b"keep")
    assert client.post("/api/datasets/source/rename", json={"name": target}).status_code == 409
    assert source.is_dir()
    assert (root / "existing-file").read_bytes() == b"keep"


def test_rename_missing_source(workspace):
    _, _, client = workspace
    assert client.post("/api/datasets/missing/rename", json={"name": "target"}).status_code == 404


@pytest.mark.parametrize("busy", ["source", "target"])
def test_rename_rejects_in_use_source_or_target(workspace, monkeypatch, busy):
    root, source, client = workspace
    monkeypatch.setattr(tm, "dump", lambda: [
        {"status": "RUNNING", "metadata": {"config": {"train_data_dir": str(root / busy)}}}
    ])
    # Match the existing task-config boundary without needing a training process.
    monkeypatch.setattr("mikazuki.datasets.inuse.resolve_task_config", lambda metadata: metadata["config"])
    assert client.post("/api/datasets/source/rename", json={"name": "target"}).status_code == 409
    assert source.is_dir()
    assert not (root / "target").exists()


@pytest.mark.parametrize("locked", ["source", "target"])
def test_rename_respects_both_operation_locks(workspace, locked):
    _, source, client = workspace
    with locks.lock_for(locked):
        response = client.post("/api/datasets/source/rename", json={"name": "target"})
    assert response.status_code == 409
    assert source.is_dir()
    assert client.post("/api/datasets/source/rename", json={"name": "target"}).status_code == 200


def test_contents_root_contract(workspace):
    _, source, client = workspace
    response = client.get("/api/datasets/source/contents")
    assert response.status_code == 200
    assert response.json()["data"] == {
        "name": "source", "path": normalize_path(source), "relative_path": "",
        "entries": [
            {"name": "sub", "path": "sub", "kind": "directory"},
            {"name": "a.PNG", "path": "a.PNG", "kind": "image"},
            {"name": "a.txt", "path": "a.txt", "kind": "file"},
        ],
        "in_use": False,
    }


def test_contents_nested_contract_and_in_use(workspace, monkeypatch):
    _, source, client = workspace
    monkeypatch.setattr("mikazuki.datasets.api.datasets_in_use", lambda root: {"source"})
    response = client.get("/api/datasets/source/contents", params={"path": "sub/"})
    assert response.status_code == 200
    assert response.json()["data"] == {
        "name": "source", "path": normalize_path(source / "sub"), "relative_path": "sub",
        "entries": [{"name": "nested.jpg", "path": "sub/nested.jpg", "kind": "image"}],
        "in_use": True,
    }


@pytest.mark.parametrize("path", ["../", "sub/../../", r"..\outside", "/absolute", "C:relative", "C:/absolute", ".upload-tmp", "sub/../", "bad\x00path"])
def test_contents_rejects_unsafe_paths(workspace, path):
    _, _, client = workspace
    assert client.get("/api/datasets/source/contents", params={"path": path}).status_code == 400


@pytest.mark.parametrize("name,path", [("missing", ""), ("source", "missing"), ("source", "a.txt")])
def test_contents_missing_directory(workspace, name, path):
    _, _, client = workspace
    assert client.get(f"/api/datasets/{name}/contents", params={"path": path}).status_code == 404


def test_contents_rejects_absolute_path_even_inside_dataset(workspace):
    _, source, client = workspace
    assert client.get("/api/datasets/source/contents", params={"path": str(source / "sub")}).status_code == 400


def test_contents_symlink_escape(workspace, tmp_path):
    _, source, client = workspace
    outside = tmp_path / "outside"
    outside.mkdir()
    link = source / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege unavailable")
        raise
    assert client.get("/api/datasets/source/contents", params={"path": "escape"}).status_code == 400
    entries = client.get("/api/datasets/source/contents").json()["data"]["entries"]
    assert "escape" not in {entry["name"] for entry in entries}


def make_directory_link(link, target):
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=True, capture_output=True,
        )
    else:
        link.symlink_to(target, target_is_directory=True)


def test_contents_directory_link_escape(workspace, tmp_path):
    _, source, client = workspace
    outside = tmp_path / "outside"
    outside.mkdir()
    make_directory_link(source / "escape", outside)
    assert client.get("/api/datasets/source/contents", params={"path": "escape"}).status_code == 400
    entries = client.get("/api/datasets/source/contents").json()["data"]["entries"]
    assert "escape" not in {entry["name"] for entry in entries}


def test_rename_rejects_source_directory_alias(workspace):
    root, source, client = workspace
    make_directory_link(root / "alias", source)
    response = client.post("/api/datasets/alias/rename", json={"name": "target"})
    assert response.status_code == 400
    assert source.is_dir()


def test_rename_rejects_dangling_target_directory_alias(workspace):
    root, source, client = workspace
    make_directory_link(root / "alias", root / "absent")
    response = client.post("/api/datasets/source/rename", json={"name": "alias"})
    assert response.status_code == 400
    assert source.is_dir()
    assert not (root / "absent").exists()


def test_rename_invalidates_inflight_overview(workspace, monkeypatch):
    _, source, client = workspace
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    original = stats._compute_and_store

    def slow_overview(dataset_dir):
        started.set()
        assert release.wait(5)
        return {"state": "ready", "file_count": 999}

    def observed_worker(*args):
        try:
            return original(*args)
        finally:
            completed.set()

    monkeypatch.setattr(stats, "compute_overview", slow_overview)
    monkeypatch.setattr(stats, "_compute_and_store", observed_worker)
    stats.get_overview(source)
    try:
        assert started.wait(5)
        assert client.post("/api/datasets/source/rename", json={"name": "target"}).status_code == 200
    finally:
        release.set()
        assert completed.wait(5)
    assert stats.cached_overview(source) is None

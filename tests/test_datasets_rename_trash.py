import json
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mikazuki.app.application import app
from mikazuki.app.config import app_config
from mikazuki.datasets import locks, trash
from mikazuki.tasks import tm


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    source = root / "source"
    source.mkdir(parents=True)
    (source / "a.png").write_bytes(b"original-image")
    (source / "a.txt").write_text("original-caption", encoding="utf-8")
    (source / "b.png").write_bytes(b"other-image")
    monkeypatch.setitem(app_config._stored, "datasets_root", str(root))
    monkeypatch.setattr(tm, "dump", lambda: [])
    return root, source, TestClient(app)


def delete_batch(client, path):
    response = client.request("DELETE", "/api/datasets/source/files", json={"paths": [path]})
    assert response.status_code == 200
    return response.json()["data"]["batch"]


@pytest.mark.parametrize("global_restore", [False, True])
def test_rename_retargets_trash_and_restores_to_new_name(workspace, global_restore):
    root, source, client = workspace
    batch = delete_batch(client, "a.png")
    manifest_path = root / ".trash" / batch / "manifest.json"
    original = json.loads(manifest_path.read_text(encoding="utf-8"))
    original["custom_field"] = {"keep": True}
    manifest_path.write_text(json.dumps(original), encoding="utf-8")

    assert client.post("/api/datasets/source/rename", json={"name": "target"}).status_code == 200
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == {**original, "dataset": "target"}
    assert client.get("/api/datasets/target/trash").json()["data"]["batches"][0]["id"] == batch
    endpoint = "/api/datasets-trash/restore" if global_restore else "/api/datasets/target/trash/restore"
    response = client.post(endpoint, json={"id": batch})
    assert response.status_code == 200
    assert sorted(response.json()["data"]["restored"]) == ["a.png", "a.txt"]
    assert (root / "target" / "a.png").read_bytes() == b"original-image"
    assert not source.exists()


def test_old_name_reuse_cannot_restore_or_empty_renamed_trash(workspace):
    root, source, client = workspace
    batch = delete_batch(client, "a.png")
    assert client.post("/api/datasets/source/rename", json={"name": "target"}).status_code == 200
    assert client.post("/api/datasets", json={"name": "source"}).status_code == 200
    (source / "a.png").write_bytes(b"new-dataset")
    assert client.get("/api/datasets/source/trash").json()["data"]["batches"] == []
    assert client.post("/api/datasets/source/trash/restore", json={"id": batch}).status_code == 404
    assert client.post("/api/datasets/source/trash/empty", json={"id": batch, "confirm": True}).status_code == 404
    response = client.post("/api/datasets-trash/restore", json={"id": batch})
    assert response.status_code == 200
    assert response.json()["data"]["dataset"] == "target"
    assert (source / "a.png").read_bytes() == b"new-dataset"
    assert not (source / "a.txt").exists()
    assert (root / "target" / "a.txt").read_text(encoding="utf-8") == "original-caption"


@pytest.mark.parametrize("failure", ["stage", "publish"])
def test_rename_metadata_failure_keeps_directory_and_all_manifests(workspace, monkeypatch, failure):
    root, source, client = workspace
    batches = [delete_batch(client, "a.png"), delete_batch(client, "b.png")]
    originals = {root / ".trash" / batch / "manifest.json": (root / ".trash" / batch / "manifest.json").read_bytes()
                 for batch in batches}
    real_write = Path.write_text
    real_replace = Path.replace
    calls = 0

    def fail_second_stage(path, *args, **kwargs):
        nonlocal calls
        if root / ".trash" in path.parents:
            calls += 1
            if calls == 2:
                raise OSError("simulated metadata staging failure")
        return real_write(path, *args, **kwargs)

    def fail_second_publish(path, target):
        nonlocal calls
        if Path(target) in originals:
            calls += 1
            if calls == 2:
                raise OSError("simulated metadata publication failure")
        return real_replace(path, target)

    monkeypatch.setattr(Path, "write_text", fail_second_stage)
    if failure == "publish":
        monkeypatch.setattr(Path, "write_text", real_write)
        monkeypatch.setattr(Path, "replace", fail_second_publish)
    response = client.post("/api/datasets/source/rename", json={"name": "target"})
    # A filesystem failure is reported as a retryable conflict, not a bad request.
    assert response.status_code == 409
    assert source.is_dir()
    assert not (root / "target").exists()
    for path, data in originals.items():
        assert path.read_bytes() == data
        assert sorted(item.name for item in path.parent.iterdir()) == ["files", "manifest.json"]
    assert client.post("/api/datasets-trash/restore", json={"id": batches[0]}).status_code == 200
    assert (source / "a.png").read_bytes() == b"original-image"


@pytest.mark.parametrize("operation", ["restore", "empty-single", "empty-all"])
def test_global_trash_operation_rechecks_owner_after_lock(workspace, monkeypatch, operation):
    root, source, client = workspace
    batch = delete_batch(client, "a.png")
    original_operation = trash.dataset_operation
    renamed = False

    @contextmanager
    def rename_before_lock(name):
        nonlocal renamed
        if not renamed:
            renamed = True
            assert client.post("/api/datasets/source/rename", json={"name": "target"}).status_code == 200
        with original_operation(name):
            yield

    monkeypatch.setattr(trash, "dataset_operation", rename_before_lock)
    if operation == "restore":
        response = client.post("/api/datasets-trash/restore", json={"id": batch})
    else:
        payload = {"confirm": True}
        if operation == "empty-single":
            payload["id"] = batch
        response = client.post("/api/datasets-trash/empty", json=payload)
    assert response.status_code == 409
    assert not source.exists()
    assert (root / ".trash" / batch / "files" / "a.png").read_bytes() == b"original-image"
    assert (root / "target").is_dir()


def test_rename_rejects_target_with_unrestored_trash(workspace):
    root, source, client = workspace
    target = root / "target"
    target.mkdir()
    (target / "foreign.png").write_bytes(b"foreign-dataset")
    batch = client.delete("/api/datasets/target").json()["data"]["batch"]
    assert client.post("/api/datasets/source/rename", json={"name": "target"}).status_code == 409
    assert source.is_dir()
    assert not target.exists()
    assert client.post("/api/datasets-trash/restore", json={"id": batch}).status_code == 200
    assert (target / "foreign.png").read_bytes() == b"foreign-dataset"


def test_rename_directory_move_failure_preserves_trash(workspace, monkeypatch):
    root, source, client = workspace
    batch = delete_batch(client, "a.png")
    manifest_path = root / ".trash" / batch / "manifest.json"
    original = manifest_path.read_bytes()
    real_rename = Path.rename

    def fail_directory_move(path, target):
        if path == source:
            raise OSError("simulated directory move failure")
        return real_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_directory_move)
    assert client.post("/api/datasets/source/rename", json={"name": "target"}).status_code == 409
    assert source.is_dir()
    assert not (root / "target").exists()
    assert manifest_path.read_bytes() == original
    assert sorted(path.name for path in manifest_path.parent.iterdir()) == ["files", "manifest.json"]


def test_rename_holds_both_locks_while_publishing_metadata(workspace, monkeypatch):
    root, _, client = workspace
    batch = delete_batch(client, "a.png")
    manifest_path = root / ".trash" / batch / "manifest.json"
    real_replace = Path.replace
    acquired = {}

    def publish_under_locks(path, target):
        if Path(target) == manifest_path:
            def probe_locks():
                for name in ("source", "target"):
                    lock = locks.lock_for(name)
                    acquired[name] = lock.acquire(blocking=False)
                    if acquired[name]:
                        lock.release()

            thread = threading.Thread(target=probe_locks)
            thread.start()
            thread.join(timeout=5)
            assert not thread.is_alive()
        return real_replace(path, target)

    monkeypatch.setattr(Path, "replace", publish_under_locks)
    assert client.post("/api/datasets/source/rename", json={"name": "target"}).status_code == 200
    assert acquired == {"source": False, "target": False}

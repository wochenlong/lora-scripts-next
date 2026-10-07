import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from mikazuki.dataset_editor import router
from mikazuki.tagger.caption_store import CaptionJobStore


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    store = CaptionJobStore(tmp_path / "state.sqlite3")
    monkeypatch.setattr("mikazuki.llm.runtime.caption_job_store", store)
    Image.new("RGB", (16, 16)).save(tmp_path / "a.png")
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        yield tmp_path, store, client


def seed(root, store, content, caption_format, tags=None):
    path = root / "a.txt"
    path.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    store.remember_format(path, sha, caption_format, tags)
    return sha


def test_short_natural_caption_preserves_raw_bytes_and_blocks_tag_batch(dataset):
    root, store, client = dataset
    original = "  猫\r\n".encode()
    before = seed(root, store, original, "natural")
    item = client.post("/api/dataset-editor/scan", json={"path": str(root)}).json()["data"]["items"][0]
    assert item["caption_format"] == "natural"
    assert item["tags"] == []
    assert item["caption"] == original.decode()
    assert item["caption_sha256"] == before
    assert client.post("/api/dataset-editor/batch", json={"root": str(root), "images": ["a.png"], "clean": True}).status_code == 409
    updated = "   狗\r\n"
    response = client.post("/api/dataset-editor/caption", json={"root": str(root), "image": "a.png", "caption": updated, "expected_sha256": before})
    assert response.status_code == 200
    assert response.json()["data"]["caption_format"] == "natural"
    assert (root / "a.txt").read_bytes() == updated.encode()
    assert client.post("/api/dataset-editor/undo", json={"root": str(root)}).status_code == 200
    assert (root / "a.txt").read_bytes() == original


def test_caption_first_mixed_uses_actual_training_tags_not_short_natural_text(dataset):
    root, store, client = dataset
    seed(root, store, "猫\n\ncat, window".encode(), "mixed", ["cat", "window"])
    item = client.post("/api/dataset-editor/scan", json={"path": str(root)}).json()["data"]["items"][0]
    assert item["caption_format"] == "mixed"
    assert item["tags"] == ["cat", "window"]
    assert item["natural_text"] == "猫"


def test_editor_rejects_stale_scan_hash_without_overwriting_external_edit(dataset):
    root, store, client = dataset
    before = seed(root, store, "猫".encode(), "natural")
    (root / "a.txt").write_text("external user edit", encoding="utf-8")
    response = client.post("/api/dataset-editor/caption", json={"root": str(root), "image": "a.png", "caption": "new caption", "expected_sha256": before})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "caption_conflict"
    assert (root / "a.txt").read_text() == "external user edit"


def test_old_format_table_is_migrated_without_losing_format(tmp_path):
    import sqlite3
    path = tmp_path / "state.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE caption_formats(path TEXT PRIMARY KEY, after_hash TEXT, format TEXT)")
    store = CaptionJobStore(path)
    store.remember_format(tmp_path / "a.txt", "sha", "natural")
    assert store.find_format(tmp_path / "a.txt", "sha") == "natural"


@pytest.mark.parametrize("kind", ["undo", "redo"])
@pytest.mark.parametrize("external", [b"external edit", None])
def test_history_conflict_preserves_external_change_and_stack(dataset, kind, external):
    root, store, client = dataset
    before = seed(root, store, b"cat", "tag")
    assert client.post("/api/dataset-editor/caption", json={"root": str(root), "image": "a.png", "caption": "dog", "expected_sha256": before}).status_code == 200
    if kind == "redo":
        assert client.post("/api/dataset-editor/undo", json={"root": str(root)}).status_code == 200
    if external is None:
        (root / "a.txt").unlink()
    else:
        (root / "a.txt").write_bytes(external)
    previous = client.post("/api/dataset-editor/history", json={"root": str(root)}).json()["data"]
    response = client.post(f"/api/dataset-editor/{kind}", json={"root": str(root)})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "caption_conflict"
    assert ((root / "a.txt").read_bytes() if (root / "a.txt").exists() else None) == external
    assert client.post("/api/dataset-editor/history", json={"root": str(root)}).json()["data"] == previous


def test_batch_stale_hash_rejects_all_before_mutation(dataset):
    root, store, client = dataset
    first = seed(root, store, b"cat", "tag")
    Image.new("RGB", (16, 16)).save(root / "b.png")
    (root / "b.txt").write_bytes(b"dog")
    second = hashlib.sha256(b"dog").hexdigest()
    (root / "b.txt").write_bytes(b"external edit")
    response = client.post("/api/dataset-editor/batch", json={"root": str(root), "images": ["a.png", "b.png"], "append": ["solo"], "expected_hashes": {"a.png": first, "b.png": second}})
    assert response.status_code == 409
    assert (root / "a.txt").read_bytes() == b"cat"
    assert (root / "b.txt").read_bytes() == b"external edit"


def test_partial_batch_race_keeps_successful_files_undoable(dataset, monkeypatch):
    import mikazuki.dataset_editor as editor
    root, store, client = dataset
    seed(root, store, b"cat", "tag")
    Image.new("RGB", (16, 16)).save(root / "b.png")
    (root / "b.txt").write_bytes(b"dog")
    original = editor.write_caption
    def race(image, caption, **kwargs):
        if image.name == "b.png":
            (root / "b.txt").write_bytes(b"external edit")
        return original(image, caption, **kwargs)
    monkeypatch.setattr(editor, "write_caption", race)
    response = client.post("/api/dataset-editor/batch", json={"root": str(root), "images": ["a.png", "b.png"], "append": ["solo"]})
    assert response.status_code == 409
    assert (root / "a.txt").read_bytes() == b"cat, solo"
    assert (root / "b.txt").read_bytes() == b"external edit"
    assert client.post("/api/dataset-editor/undo", json={"root": str(root)}).status_code == 200
    assert (root / "a.txt").read_bytes() == b"cat"
    assert (root / "b.txt").read_bytes() == b"external edit"


def test_tag_undo_restores_exact_whitespace_bytes_and_redo(dataset):
    root, store, client = dataset
    original = b"  cat, window\r\n"
    seed(root, store, original, "tag")
    assert client.post("/api/dataset-editor/caption", json={"root": str(root), "image": "a.png", "caption": "dog"}).status_code == 200
    assert client.post("/api/dataset-editor/undo", json={"root": str(root)}).status_code == 200
    assert (root / "a.txt").read_bytes() == original
    assert client.post("/api/dataset-editor/redo", json={"root": str(root)}).status_code == 200
    assert (root / "a.txt").read_bytes() == b"dog"


def test_multi_file_undo_preflight_does_not_partially_restore(dataset):
    root, store, client = dataset
    seed(root, store, b"cat", "tag")
    Image.new("RGB", (16, 16)).save(root / "b.png")
    (root / "b.txt").write_bytes(b"dog")
    assert client.post("/api/dataset-editor/batch", json={"root": str(root), "images": ["a.png", "b.png"], "append": ["solo"]}).status_code == 200
    (root / "b.txt").write_bytes(b"external edit")
    assert client.post("/api/dataset-editor/undo", json={"root": str(root)}).status_code == 409
    assert (root / "a.txt").read_bytes() == b"cat, solo"
    assert (root / "b.txt").read_bytes() == b"external edit"
    assert client.post("/api/dataset-editor/history", json={"root": str(root)}).json()["data"]["can_redo"] is False


def test_partial_undo_race_retains_both_history_portions(dataset, monkeypatch):
    import mikazuki.dataset_editor as editor
    root, store, client = dataset
    seed(root, store, b"cat", "tag")
    Image.new("RGB", (16, 16)).save(root / "b.png")
    (root / "b.txt").write_bytes(b"dog")
    assert client.post("/api/dataset-editor/batch", json={"root": str(root), "images": ["a.png", "b.png"], "append": ["solo"]}).status_code == 200
    original = editor.restore_caption
    def race(root_path, snapshot, expected):
        if snapshot.image == "b.png":
            (root / "b.txt").write_bytes(b"external edit")
        return original(root_path, snapshot, expected)
    monkeypatch.setattr(editor, "restore_caption", race)
    assert client.post("/api/dataset-editor/undo", json={"root": str(root)}).status_code == 409
    assert (root / "a.txt").read_bytes() == b"cat"
    assert (root / "b.txt").read_bytes() == b"external edit"
    history = client.post("/api/dataset-editor/history", json={"root": str(root)}).json()["data"]
    assert history["can_undo"] and history["can_redo"]
    assert history["changes"][0]["count"] == 1
    assert client.post("/api/dataset-editor/redo", json={"root": str(root)}).status_code == 200
    assert (root / "a.txt").read_bytes() == b"cat, solo"
    assert (root / "b.txt").read_bytes() == b"external edit"


def test_undo_caption_creation_rejects_external_replacement(dataset):
    root, _, client = dataset
    assert client.post("/api/dataset-editor/caption", json={"root": str(root), "image": "a.png", "caption": "cat"}).status_code == 200
    (root / "a.txt").write_bytes(b"external edit")
    assert client.post("/api/dataset-editor/undo", json={"root": str(root)}).status_code == 409
    assert (root / "a.txt").read_bytes() == b"external edit"


def test_mixed_undo_redo_preserves_raw_text_and_actual_tags(dataset):
    root, store, client = dataset
    original = "  猫\r\n\r\ncat, window\r\n".encode()
    before = seed(root, store, original, "mixed", ["cat", "window"])
    assert client.post("/api/dataset-editor/caption", json={"root": str(root), "image": "a.png", "caption": "狗\n\ncat, window", "expected_sha256": before}).status_code == 200
    assert client.post("/api/dataset-editor/undo", json={"root": str(root)}).status_code == 200
    assert (root / "a.txt").read_bytes() == original
    response = client.post("/api/dataset-editor/redo", json={"root": str(root)})
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["caption_format"] == "mixed"
    assert response.json()["data"]["items"][0]["tags"] == ["cat", "window"]

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

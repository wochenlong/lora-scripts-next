"""Editor, native Tag and Caption commits must preserve the same write boundary."""
import asyncio
import hashlib
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from mikazuki import dataset_editor as editor
from mikazuki.tagger import caption_write
from mikazuki.tagger.caption_job import CaptionPersistenceError, CaptionWriteConflict, caption_sha256, write_caption_atomic
from mikazuki.tagger.caption_store import CaptionJobStore


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    store = CaptionJobStore(tmp_path / "state.sqlite3")
    monkeypatch.setattr("mikazuki.llm.runtime.caption_job_store", store)
    Image.new("RGB", (8, 8)).save(tmp_path / "a.png")
    app = FastAPI()
    app.include_router(editor.router, prefix="/api")
    with TestClient(app) as client:
        yield tmp_path, store, client


@pytest.mark.parametrize("first", ["editor", "caption"])
def test_same_hash_editor_and_caption_writers_cannot_both_succeed(dataset, monkeypatch, first):
    root, store, _ = dataset
    target = root / "a.txt"
    target.write_bytes(b"before")
    expected = caption_sha256(target)
    blocked = threading.Event()
    release = threading.Event()
    results = []
    replace = caption_write.os.replace

    def pause_first(source, destination):
        if Path(destination) == target and not blocked.is_set():
            blocked.set()
            assert release.wait(3)
        replace(source, destination)

    monkeypatch.setattr(caption_write.os, "replace", pause_first)

    def run(kind):
        try:
            if kind == "editor":
                asyncio.run(editor.save_caption(editor.CaptionWriteRequest(
                    root=str(root), image="a.png", caption="user draft", expected_sha256=expected)))
            else:
                write_caption_atomic(target, "background caption", expected_sha256=expected)
            results.append((kind, "success"))
        except (CaptionWriteConflict, HTTPException) as error:
            assert isinstance(error, CaptionWriteConflict) or error.status_code == 409
            results.append((kind, "conflict"))

    first_thread = threading.Thread(target=run, args=(first,))
    second_thread = threading.Thread(target=run, args=("caption" if first == "editor" else "editor",))
    first_thread.start()
    assert blocked.wait(3)
    second_thread.start()
    time.sleep(.03)
    assert results == []
    release.set()
    for thread in [first_thread, second_thread]:
        thread.join(3)
        assert not thread.is_alive()
    assert results == [(first, "success"), ("caption" if first == "editor" else "editor", "conflict")]
    assert target.read_text().strip() == ("user draft" if first == "editor" else "background caption")
    if first == "editor":
        history = asyncio.run(editor.history(editor.UndoRequest(root=str(root))))
        assert history.data["can_undo"]
        assert store.find_format(target, caption_sha256(target)) == "unknown"


@pytest.mark.parametrize("original", [None, b"  original\r\n"])
def test_editor_metadata_failure_compensates_bytes_and_does_not_add_history(dataset, monkeypatch, original):
    root, store, client = dataset
    target = root / "a.txt"
    if original is not None:
        target.write_bytes(original)
        store.remember_format(target, caption_sha256(target), "natural", writer_job_id="prior-owner")
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("fixture database offline")
    monkeypatch.setattr(store, "remember_format", fail)
    response = client.post("/api/dataset-editor/caption", json={
        "root": str(root), "image": "a.png", "caption": "A cat.",
        "expected_sha256": caption_sha256(target),
    })
    assert response.status_code == 503
    assert (target.read_bytes() if target.is_file() else None) == original
    assert store.get_write_intent(target) is None
    assert not client.post("/api/dataset-editor/history", json={"root": str(root)}).json()["data"]["can_undo"]
    if original is not None:
        assert store.format_owner(target, caption_sha256(target)) == "prior-owner"


def test_editor_commit_does_not_need_another_database_read_to_register_undo(dataset, monkeypatch):
    root, store, client = dataset
    finish = store.finish_write_intent
    def offline(*args, **kwargs):
        raise sqlite3.OperationalError("fixture read outage after commit")
    def committed(*args, **kwargs):
        finish(*args, **kwargs)
        monkeypatch.setattr(store, "get_write_intent", offline)
        monkeypatch.setattr(store, "find_format_detail", offline)
    monkeypatch.setattr(store, "finish_write_intent", committed)
    response = client.post("/api/dataset-editor/caption", json={
        "root": str(root), "image": "a.png", "caption": "A cat.", "expected_sha256": None,
    })
    assert response.status_code == 200
    assert (root / "a.txt").read_bytes() == b"A cat."
    history = client.post("/api/dataset-editor/history", json={"root": str(root)}).json()["data"]
    assert history["can_undo"]
    assert history["changes"][0]["items"][0]["after"] == "A cat."


def test_editor_compensation_failure_leaves_durable_intent_and_next_scan_recovers(dataset, monkeypatch):
    root, store, client = dataset
    target = root / "a.txt"
    target.write_bytes(b"original\r\n")
    restore = store.restore_write_intent
    finish = store.finish_write_intent
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("fixture offline")
    monkeypatch.setattr(store, "finish_write_intent", fail)
    monkeypatch.setattr(store, "restore_write_intent", fail)
    response = client.post("/api/dataset-editor/caption", json={"root": str(root), "image": "a.png", "caption": "new"})
    assert response.status_code == 503
    assert target.read_bytes() == b"original\r\n"
    assert store.get_write_intent(target) is not None
    monkeypatch.setattr(store, "restore_write_intent", restore)
    monkeypatch.setattr(store, "finish_write_intent", finish)
    assert client.post("/api/dataset-editor/scan", json={"path": str(root)}).status_code == 200
    assert store.get_write_intent(target) is None
    assert target.read_bytes() == b"original\r\n"


def test_editor_intent_never_overwrites_external_change(dataset):
    root, store, client = dataset
    target = root / "a.txt"
    store.prepare_write_intent(target, b"before", hashlib.sha256(b"before").hexdigest(), hashlib.sha256(b"pending").hexdigest())
    target.write_bytes(b"external")
    response = client.post("/api/dataset-editor/caption", json={"root": str(root), "image": "a.png", "caption": "another"})
    assert response.status_code == 409
    assert target.read_bytes() == b"external"
    assert store.get_write_intent(target) is not None


def test_recovery_scan_respects_training_occupancy(dataset, monkeypatch):
    root, store, client = dataset
    target = root / "a.txt"
    before_hash = hashlib.sha256(b"before").hexdigest()
    after_hash = hashlib.sha256(b"pending").hexdigest()
    store.prepare_write_intent(target, b"before", before_hash, after_hash)
    target.write_bytes(b"pending")
    def busy(path):
        raise HTTPException(status_code=409, detail="fixture training owns dataset")
    monkeypatch.setattr("mikazuki.datasets.inuse.ensure_path_not_in_use", busy)
    assert client.post("/api/dataset-editor/scan", json={"path": str(root)}).status_code == 409
    assert target.read_bytes() == b"pending"
    assert store.get_write_intent(target) is not None
    monkeypatch.setattr("mikazuki.datasets.inuse.ensure_path_not_in_use", lambda path: None)
    assert client.post("/api/dataset-editor/scan", json={"path": str(root)}).status_code == 200
    assert target.read_bytes() == b"before"


@pytest.mark.parametrize("after_exists", [False, True])
def test_editor_process_exit_before_provenance_recovers_original_on_scan(dataset, after_exists):
    root, store, client = dataset
    target = root / "a.txt"
    original = b"before\r\n" if after_exists else None
    if original is not None:
        target.write_bytes(original)
        store.remember_format(target, caption_sha256(target), "natural")
    script = r'''
import os, sys
from pathlib import Path
from mikazuki.tagger.caption_store import CaptionJobStore
from mikazuki.tagger.caption_write import commit_caption_write
from mikazuki.tagger.caption_job import caption_sha256
store=CaptionJobStore(sys.argv[1])
store.finish_write_intent=lambda *args, **kwargs: os._exit(87)
path=Path(sys.argv[2])
commit_caption_write(store,path,b"uncommitted",expected_sha256=caption_sha256(path),caption_format="natural")
'''
    process = subprocess.run([sys.executable, "-c", script, str(store.path), str(target)], capture_output=True, timeout=15)
    assert process.returncode == 87, process.stderr.decode(errors="replace")
    assert target.read_bytes() == b"uncommitted"
    assert client.post("/api/dataset-editor/scan", json={"path": str(root)}).status_code == 200
    assert (target.read_bytes() if target.exists() else None) == original
    assert store.get_write_intent(target) is None


def test_format_confirmation_preserves_bytes_and_checks_hash(dataset):
    root, store, client = dataset
    target = root / "a.txt"
    raw = b"  A cat, sleeping on grass\r\n"
    target.write_bytes(raw)
    scan = client.post("/api/dataset-editor/scan", json={"path": str(root)}).json()["data"]["items"][0]
    assert scan["caption_format"] == "unknown"
    assert scan["caption"] == raw.decode()
    assert scan["tags"] == []
    batch = {"root": str(root), "images": ["a.png"], "remove": ["A cat"]}
    assert client.post("/api/dataset-editor/batch", json=batch).status_code == 409
    request = {"root": str(root), "image": "a.png", "caption_format": "natural", "expected_sha256": scan["caption_sha256"]}
    response = client.post("/api/dataset-editor/caption/format", json=request)
    assert response.status_code == 200
    assert response.json()["data"]["caption_format"] == "natural"
    assert target.read_bytes() == raw
    request["caption_format"] = "tag"
    response = client.post("/api/dataset-editor/caption/format", json=request)
    assert response.status_code == 200
    assert response.json()["data"]["tags"] == ["A cat", "sleeping on grass"]
    assert target.read_bytes() == raw
    assert client.post("/api/dataset-editor/batch", json=batch).status_code == 200
    assert target.read_text() == "sleeping on grass"
    assert client.post("/api/dataset-editor/caption/format", json=request).status_code == 409
    request.pop("expected_sha256")
    assert client.post("/api/dataset-editor/caption/format", json=request).status_code == 422


def test_new_tag_editor_save_is_explicit_and_natural_cannot_be_downgraded(dataset):
    root, store, client = dataset
    payload = {"root": str(root), "image": "a.png", "caption": "cat, grass", "caption_format": "tag", "expected_sha256": None}
    response = client.post("/api/dataset-editor/caption", json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["caption_format"] == "tag"
    target = root / "a.txt"
    store.remember_format(target, caption_sha256(target), "natural")
    payload["expected_sha256"] = caption_sha256(target)
    assert client.post("/api/dataset-editor/caption", json=payload).status_code == 409
    assert target.read_text() == "cat, grass"

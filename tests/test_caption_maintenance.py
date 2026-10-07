import hashlib
import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikazuki.llm.contracts import LLMProfile
from mikazuki.tagger.caption_job import CaptionJobManager, caption_sha256
from mikazuki.tagger.caption_store import CaptionJobStore
from mikazuki.tagger.caption_maintenance import delete_history, rollback_job
from mikazuki.tagger.progress import tagger_progress


class Vision:
    async def complete_vision(self, image, prompt, **kwargs):
        return LLMProfile(id="fake", name="fake", endpoint="http://localhost:8080/v1/chat/completions", model="fake", source="local-endpoint", capabilities=("vision",)), {"choices": [{"finish_reason": "stop"}]}, json.dumps({"caption": "一只猫。", "language": "zh-CN"}), {}


@pytest.fixture
def completed(tmp_path):
    (tmp_path / "a.png").write_bytes(b"fake-image")
    store = CaptionJobStore(tmp_path / "state.sqlite3")
    manager = CaptionJobManager(Vision(), job_store=store)
    yield tmp_path, store, manager
    tagger_progress.release()


def run(manager, root):
    manager.start({"path": str(root), "mode": "natural"})
    manager._thread.join(5)
    assert manager.status()["succeeded"] == 1
    return manager.status()["job_id"]


def test_rollback_restores_original_natural_bytes_format_and_is_idempotent(completed):
    root, store, manager = completed
    original = "  猫\r\n".encode()
    (root / "a.txt").write_bytes(original)
    store.remember_format(root / "a.txt", hashlib.sha256(original).hexdigest(), "natural")
    job = run(manager, root)
    result = rollback_job(manager, job)
    assert result["restored"] == 1
    assert (root / "a.txt").read_bytes() == original
    assert store.find_format(root / "a.txt", caption_sha256(root / "a.txt")) == "natural"
    assert rollback_job(manager, job)["skipped"] == 1


def test_rollback_creation_removes_only_unchanged_caption(completed):
    root, _, manager = completed
    job = run(manager, root)
    assert rollback_job(manager, job)["restored"] == 1
    assert not (root / "a.txt").exists()


def test_external_edit_rejects_rollback_without_overwrite(completed):
    root, _, manager = completed
    job = run(manager, root)
    (root / "a.txt").write_bytes(b"external edit")
    assert rollback_job(manager, job)["conflicts"] == 1
    assert (root / "a.txt").read_bytes() == b"external edit"


def test_later_job_same_bytes_protects_ownership_and_supports_reverse_rollback(completed):
    root, _, manager = completed
    old = run(manager, root)
    new = run(manager, root)
    assert rollback_job(manager, old)["conflicts"] == 1
    assert rollback_job(manager, new)["restored"] == 1
    assert rollback_job(manager, old)["restored"] == 1
    assert not (root / "a.txt").exists()


def test_history_clear_preserves_caption_and_provenance(completed):
    root, store, manager = completed
    job = run(manager, root)
    content = (root / "a.txt").read_bytes()
    delete_history(manager, job)
    assert store.get(job) is None
    assert store.get_backup(job, 0) is None
    assert store.find_format(root / "a.txt", caption_sha256(root / "a.txt")) == "natural"
    assert (root / "a.txt").read_bytes() == content
    assert manager.status()["phase"] == "idle"


def test_rollback_resumes_after_file_restore_before_metadata_commit(completed, monkeypatch):
    root, store, manager = completed
    (root / "a.txt").write_bytes(b"cat, window\r\n")
    job = run(manager, root)
    original = store.remember_format
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("fixture database offline")
    monkeypatch.setattr(store, "remember_format", fail)
    with pytest.raises(sqlite3.Error):
        rollback_job(manager, job)
    assert (root / "a.txt").read_bytes() == b"cat, window\r\n"
    monkeypatch.setattr(store, "remember_format", original)
    assert rollback_job(manager, job)["restored"] == 1
    assert store.find_format(root / "a.txt", caption_sha256(root / "a.txt")) == "tag"


def test_busy_reservation_blocks_maintenance(completed):
    root, _, manager = completed
    job = run(manager, root)
    assert tagger_progress.try_begin("tagging", "", "busy")
    with pytest.raises(RuntimeError):
        rollback_job(manager, job)
    with pytest.raises(RuntimeError):
        delete_history(manager, job)


def test_maintenance_api_response_excludes_backups_and_private_paths(completed, monkeypatch):
    from mikazuki.tagger import caption_api
    root, _, manager = completed
    job = run(manager, root)
    monkeypatch.setattr(caption_api, "caption_job_manager", manager)
    app = FastAPI()
    app.include_router(caption_api.router, prefix="/api")
    with TestClient(app) as client:
        response = client.post(f"/api/tagger/jobs/{job}/rollback")
        assert response.status_code == 200
        assert response.json()["data"]["restored"] == 1
        assert "content" not in response.text
        assert str(root) not in response.text
        assert client.delete(f"/api/tagger/jobs/{job}").status_code == 200
        assert client.get(f"/api/tagger/jobs/{job}").status_code == 404


def test_manual_save_same_bytes_changes_owner_and_prevents_old_rollback(completed):
    root, store, manager = completed
    job = run(manager, root)
    store.remember_format(root / "a.txt", caption_sha256(root / "a.txt"), "natural")
    assert rollback_job(manager, job)["conflicts"] == 1
    assert (root / "a.txt").exists()


def test_corrupted_backup_cannot_be_restored(completed):
    root, store, manager = completed
    (root / "a.txt").write_bytes(b"original")
    job = run(manager, root)
    generated = (root / "a.txt").read_bytes()
    with store._connect() as connection:
        connection.execute("UPDATE caption_backups SET content=? WHERE job_id=?", (b"corrupted", job))
    assert rollback_job(manager, job)["skipped"] == 1
    assert (root / "a.txt").read_bytes() == generated


def test_database_failure_before_restore_leaves_caption_unchanged(completed, monkeypatch):
    root, store, manager = completed
    job = run(manager, root)
    generated = (root / "a.txt").read_bytes()
    def fail(*args):
        raise sqlite3.OperationalError("fixture database offline")
    monkeypatch.setattr(store, "mark_rollback", fail)
    with pytest.raises(sqlite3.Error):
        rollback_job(manager, job)
    assert (root / "a.txt").read_bytes() == generated


def test_rollback_owner_is_rechecked_after_temp_file_write(completed, monkeypatch):
    from mikazuki.tagger import caption_maintenance as maintenance
    root, store, manager = completed
    (root / "a.txt").write_bytes(b"original")
    job = run(manager, root)
    generated = (root / "a.txt").read_bytes()
    original = maintenance.os.fsync
    def later_writer(fd):
        original(fd)
        store.remember_format(root / "a.txt", caption_sha256(root / "a.txt"), "natural")
    monkeypatch.setattr(maintenance.os, "fsync", later_writer)
    assert rollback_job(manager, job)["conflicts"] == 1
    assert (root / "a.txt").read_bytes() == generated
    assert not list(root.glob("*.tmp"))

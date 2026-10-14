"""Recover every pending write before admitting a new task or rollback."""
import copy
import hashlib
import sqlite3
import time

import pytest
from fastapi import HTTPException

from mikazuki.llm.contracts import LLMProfile
from mikazuki.tagger.caption_job import CaptionJobManager, CaptionPersistenceError, caption_sha256
from mikazuki.tagger.caption_store import CaptionJobStore
from mikazuki.tagger.progress import tagger_progress


def prepared_rollback(root, monkeypatch, original=b"cat, window\r\n"):
    """Real rollback reaches file restoration, then its metadata commit fails."""
    from mikazuki.tagger.caption_maintenance import rollback_job
    image = root / "a.png"
    image.write_bytes(b"image")
    target = image.with_suffix(".txt")
    store = CaptionJobStore(root / "jobs.sqlite3")
    if original is not None:
        target.write_bytes(original)
        store.remember_format(target, caption_sha256(target), "tag", ["cat", "window"], "prior-owner")
    service = Vision()
    manager = CaptionJobManager(service, job_store=store)
    job_id = manager.start({"path": str(root), "mode": "natural", "conflict_action": "copy"})["job_id"]
    wait(manager)
    method = "forget_format" if original is None else "remember_format"
    restore = getattr(store, method)
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("fixture rollback provenance offline")
    monkeypatch.setattr(store, method, fail)
    with pytest.raises(sqlite3.Error):
        rollback_job(manager, job_id)
    assert (target.read_bytes() if target.exists() else None) == original
    assert store.rollback_status(job_id, 0) == "prepared"
    return store, manager, service, job_id, target, method, restore


@pytest.mark.parametrize("original", [None, b"cat, window\r\n"])
def test_prepared_rollback_storage_failure_blocks_start_restart_and_history_delete(tmp_path, monkeypatch, original):
    from mikazuki.tagger.caption_maintenance import delete_history
    store, manager, service, job_id, target, method, restore = prepared_rollback(tmp_path, monkeypatch, original)
    for operation in [lambda: manager.start({"path": str(tmp_path), "mode": "natural"}),
                      lambda: CaptionJobManager(Vision(), job_store=store),
                      lambda: delete_history(manager, job_id)]:
        with pytest.raises(CaptionPersistenceError):
            operation()
        assert store.rollback_status(job_id, 0) == "prepared"
        assert store.get_backup(job_id, 0) is not None
        assert (target.read_bytes() if target.exists() else None) == original
    assert service.calls == ["a.png"]
    monkeypatch.setattr(store, method, restore)
    empty = tmp_path / "empty"
    empty.mkdir()
    manager.start({"path": str(empty), "mode": "natural"})
    wait(manager)
    assert store.rollback_status(job_id, 0) == "done"
    if original is None:
        assert store.format_record(target) is None
    else:
        assert store.find_format_detail(target, caption_sha256(target)) == {"format": "tag", "tags": ["cat", "window"]}
        assert store.format_owner(target, caption_sha256(target)) == "prior-owner"


@pytest.mark.parametrize("original", [None, b"cat, window\r\n"])
def test_restart_finishes_prepared_rollback_without_inference(tmp_path, monkeypatch, original):
    store, _manager, service, job_id, target, method, restore = prepared_rollback(tmp_path, monkeypatch, original)
    monkeypatch.setattr(store, method, restore)
    restored = CaptionJobManager(Vision(), job_store=CaptionJobStore(store.path))
    assert restored.status()["job_id"] == job_id
    assert store.rollback_status(job_id, 0) == "done"
    assert (target.read_bytes() if target.exists() else None) == original
    assert service.calls == ["a.png"]
    if original is not None:
        assert store.find_format(target, caption_sha256(target)) == "tag"


@pytest.mark.parametrize("boundary", ["external-text", "new-owner", "backup-tamper", "training"])
def test_prepared_rollback_conflicts_preserve_bytes_and_block_mutations(tmp_path, monkeypatch, boundary):
    from mikazuki.tagger.caption_maintenance import delete_history
    store, manager, _service, job_id, target, method, restore = prepared_rollback(tmp_path, monkeypatch)
    monkeypatch.setattr(store, method, restore)
    if boundary == "external-text":
        target.write_bytes(b"external user text")
    elif boundary == "new-owner":
        store.remember_format(target, caption_sha256(target), "natural", writer_job_id="manual-other")
    elif boundary == "backup-tamper":
        with store._connect() as connection:
            connection.execute("UPDATE caption_backups SET content=? WHERE job_id=?", (b"tampered", job_id))
    else:
        def busy(path):
            raise HTTPException(status_code=409, detail="fixture training in use")
        monkeypatch.setattr("mikazuki.datasets.inuse.ensure_path_not_in_use", busy)
    before = target.read_bytes()
    with pytest.raises(CaptionPersistenceError):
        manager.start({"path": str(tmp_path), "mode": "natural"})
    with pytest.raises(CaptionPersistenceError):
        delete_history(manager, job_id)
    assert target.read_bytes() == before
    assert store.rollback_status(job_id, 0) == "prepared"
    assert store.get_backup(job_id, 0) is not None


@pytest.fixture(autouse=True)
def idle():
    tagger_progress.reset_idle()
    yield
    tagger_progress.reset_idle()


class Vision:
    def __init__(self):
        self.calls = []

    async def complete_vision(self, image, *_args, **_kwargs):
        self.calls.append(image.name)
        profile = LLMProfile(id="fake", name="Fake", model="fake", source="remote",
                             endpoint="http://localhost/v1/chat/completions", capabilities=("vision",))
        return profile, {"choices": [{"finish_reason": "stop"}]}, '{"caption":"A sample image.","language":"en"}', {}


def wait(manager):
    manager._thread.join(timeout=3)
    assert not manager._thread.is_alive()
    return manager.status()


def interrupted(store, image, *, completed=False):
    before = b"Original caption.\r\n"
    after = b"A sample image.\n"
    before_hash = hashlib.sha256(before).hexdigest()
    after_hash = hashlib.sha256(after).hexdigest()
    result = {"filename": image.name, "index": 0, "status": "written", "written": True,
              "caption_format": "natural", "tags": [], "before_hash": before_hash, "after_hash": after_hash}
    state = {**CaptionJobManager._idle(), "job_id": "old", "mode": "natural", "phase": "error", "total": 1,
             "updated_at": time.time() - 10, "report": {"items": [result] if completed else []},
             "succeeded": int(completed), "current": int(completed)}
    request = {"path": str(image.parent), "mode": "natural", "language": "en", "conflict_action": "copy",
               "expected_hashes": {str(image): before_hash}}
    store.backup("old", 0, before, before_hash, {"format": "natural", "tags": [], "writer_job_id": None})
    store.save(state, request, [str(image)], [0] if completed else [], [],
               {"index": 0, "after_hash": after_hash, "result": result})
    image.with_suffix(".txt").write_bytes(after)
    return before, after


def test_all_history_recovery_keeps_latest_and_restores_old_rollback_entry(tmp_path):
    from mikazuki.tagger.caption_maintenance import rollback_job
    image = tmp_path / "a.png"
    image.write_bytes(b"image")
    store = CaptionJobStore(tmp_path / "jobs.sqlite3")
    before, after = interrupted(store, image)
    latest = {**CaptionJobManager._idle(), "job_id": "new", "phase": "done"}
    store.save(latest, {"mode": "natural"}, [], [], [])
    service = Vision()
    recovered = CaptionJobManager(service, job_store=store)
    assert recovered.status()["job_id"] == "new"
    old = recovered.detail("old")
    assert old["succeeded"] == old["current"] == 1
    assert old["report"]["items"][0]["recovered_write"]
    assert store.get("old")["recovery"]["intent"] is None
    assert store.format_owner(image.with_suffix(".txt"), caption_sha256(image.with_suffix(".txt"))) == "old"
    assert service.calls == []
    assert image.with_suffix(".txt").read_bytes() == after
    assert CaptionJobManager(Vision(), job_store=store).status()["job_id"] == "new"
    assert rollback_job(recovered, "old")["restored"] == 1
    assert image.with_suffix(".txt").read_bytes() == before


@pytest.mark.parametrize("stage", ["provenance", "save"])
def test_unresolved_storage_failure_blocks_new_task_retry_and_rollback(tmp_path, monkeypatch, stage):
    from mikazuki.tagger.caption_maintenance import rollback_job
    image = tmp_path / "a.png"
    image.write_bytes(b"image")
    store = CaptionJobStore(tmp_path / "jobs.sqlite3")
    service = Vision()
    manager = CaptionJobManager(service, job_store=store)
    _before, after = interrupted(store, image)
    method = "remember_format" if stage == "provenance" else "save"
    original = getattr(store, method)

    def failure(*_args, **_kwargs):
        raise sqlite3.OperationalError("synthetic storage fault")

    monkeypatch.setattr(store, method, failure)
    for operation in (
        lambda: manager.start({"path": str(tmp_path), "mode": "natural"}),
        lambda: manager.retry_failed("old"),
        lambda: rollback_job(manager, "old"),
    ):
        with pytest.raises(CaptionPersistenceError):
            operation()
        assert service.calls == []
        assert image.with_suffix(".txt").read_bytes() == after
        assert store.get("old")["recovery"]["intent"] is not None
        assert manager._thread is None
        assert not tagger_progress.is_busy()
    monkeypatch.setattr(store, method, original)
    manager.start({"path": str(tmp_path), "mode": "natural"})
    assert wait(manager)["skipped"] == 1
    assert service.calls == []
    assert manager.detail("old")["succeeded"] == 1


@pytest.mark.parametrize("current", ["before", "external"])
def test_recovery_preserves_before_and_external_bytes_without_inference(tmp_path, current):
    image = tmp_path / "a.png"
    image.write_bytes(b"image")
    store = CaptionJobStore(tmp_path / "jobs.sqlite3")
    before, _after = interrupted(store, image)
    content = before if current == "before" else b"An external caption."
    image.with_suffix(".txt").write_bytes(content)
    service = Vision()
    manager = CaptionJobManager(service, job_store=store)
    state = manager.status()
    assert state["succeeded"] == state["current"] == 0
    assert state["failed"] == 1
    assert state["report"]["items"][0]["code"] == ("caption_interrupted" if current == "before" else "caption_conflict")
    assert store.get("old")["recovery"]["intent"] is None
    assert image.with_suffix(".txt").read_bytes() == content
    assert service.calls == []
    manager.recover_pending()
    assert len(manager.status()["report"]["items"]) == 1
    assert image.with_suffix(".txt").read_bytes() == content


def test_completed_index_still_repairs_provenance_without_double_counts(tmp_path):
    image = tmp_path / "a.png"
    image.write_bytes(b"image")
    store = CaptionJobStore(tmp_path / "jobs.sqlite3")
    interrupted(store, image, completed=True)
    manager = CaptionJobManager(Vision(), job_store=store)
    assert manager.status()["succeeded"] == manager.status()["current"] == 1
    assert len(manager.status()["report"]["items"]) == 1
    assert store.find_format(image.with_suffix(".txt"), caption_sha256(image.with_suffix(".txt"))) == "natural"
    first = copy.deepcopy(manager.status())
    manager.recover_pending()
    assert manager.status() == first


def test_repair_does_not_steal_identical_bytes_owned_by_later_task(tmp_path):
    image = tmp_path / "a.png"
    image.write_bytes(b"image")
    store = CaptionJobStore(tmp_path / "jobs.sqlite3")
    interrupted(store, image)
    target = image.with_suffix(".txt")
    store.remember_format(target, caption_sha256(target), "natural", [], "later")
    manager = CaptionJobManager(Vision(), job_store=store)
    assert manager.detail("old")["succeeded"] == 1
    assert store.format_owner(target, caption_sha256(target)) == "later"


def test_repair_does_not_claim_same_bytes_saved_manually_after_failed_write(tmp_path):
    from mikazuki.tagger.caption_maintenance import rollback_job
    image = tmp_path / "a.png"
    image.write_bytes(b"image")
    store = CaptionJobStore(tmp_path / "jobs.sqlite3")
    _before, after = interrupted(store, image)
    target = image.with_suffix(".txt")
    # A successful manual editor save has provenance but no job owner.
    store.remember_format(target, caption_sha256(target), "natural", [], None)
    manager = CaptionJobManager(Vision(), job_store=store)
    assert manager.status()["succeeded"] == 1
    assert store.format_owner(target, caption_sha256(target)) is None
    result = rollback_job(manager, "old")
    assert result["restored"] == 0
    assert result["conflicts"] == 1
    assert target.read_bytes() == after


def test_new_snapshot_recovers_uncommitted_editor_write_first(tmp_path):
    image = tmp_path / "a.png"
    image.write_bytes(b"image")
    target = image.with_suffix(".txt")
    target.write_bytes(b"Committed original.")
    store = CaptionJobStore(tmp_path / "jobs.sqlite3")
    before_hash = caption_sha256(target)
    after = b"Uncommitted editor caption."
    store.prepare_write_intent(target, target.read_bytes(), before_hash, hashlib.sha256(after).hexdigest())
    target.write_bytes(after)
    manager = CaptionJobManager(Vision(), job_store=store)
    manager.start({"path": str(tmp_path), "mode": "natural", "conflict_action": "copy"})
    state = wait(manager)
    assert state["succeeded"] == 1
    assert manager._request["expected_hashes"][str(image)] == before_hash
    assert store.get_backup(state["job_id"], 0)["content"] == b"Committed original."
    assert store.get_write_intent(target) is None

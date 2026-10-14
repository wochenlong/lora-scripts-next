import copy

import pytest
from PIL import Image

from mikazuki.app.models import TaggerInterrogateRequest
from mikazuki.tagger import jobs, model_fetch
from mikazuki.tagger.caption_job import CaptionJobManager
from mikazuki.tagger.interrogator import available_interrogators
from mikazuki.tagger.progress import tagger_progress
from mikazuki.tagger.caption_store import CaptionJobStore
from mikazuki.tagger.caption_job import caption_sha256


@pytest.fixture(autouse=True)
def caption_store(tmp_path, monkeypatch):
    store = CaptionJobStore(tmp_path / "state.sqlite3")
    monkeypatch.setattr("mikazuki.llm.runtime.caption_job_store", store)
    return store


class TagModel:
    def load(self):
        pass

    def unload(self):
        pass

    def interrogate(self, image):
        return copy.deepcopy({"general": [("cat", .9), ("red_hair", .8), ("low", .01)], "character": [("character", .7)], "rating": [("safe", .9)], "model": [("tagger", .9)]})


class NoVision:
    async def complete_vision(self, *args, **kwargs):
        raise AssertionError("Tag mode must not call LLM")


@pytest.mark.parametrize("action", ["ignore", "copy", "prepend", "append"])
def test_new_tag_mode_matches_legacy_files_byte_for_byte(tmp_path, monkeypatch, action, caption_store):
    monkeypatch.setitem(available_interrogators, "wd14-convnextv2-v2", TagModel())
    monkeypatch.setattr(jobs, "interrogator_assets_ready", lambda *args: True)
    monkeypatch.setattr(jobs, "describe_interrogator_asset_status", lambda *args: (True, "fake assets ready"))
    monkeypatch.setattr(model_fetch, "interrogator_assets_ready", lambda *args: True)
    old, new = tmp_path / "old", tmp_path / "new"
    for root in [old, new]:
        root.mkdir()
        for name in ["a", "b", "c"]:
            Image.new("RGB", (16, 16)).save(root / (name + ".png"))
        (root / "a.txt").write_text("cat, old_tag, cat", encoding="utf-8")
        caption_store.remember_format(root / "a.txt", caption_sha256(root / "a.txt"), "tag")
        (root / "b.txt").write_text("", encoding="utf-8")
    tagger_progress.reset_idle()
    request = TaggerInterrogateRequest(path=str(old), batch_output_action_on_conflict=action, additional_tags="extra", add_rating_tag=True, add_model_tag=True)
    jobs.run_interrogate_job(request)
    assert tagger_progress.get()["phase"] == "done"
    manager = CaptionJobManager(NoVision(), job_store=caption_store)
    manager.start({**request.dict(), "path": str(new), "mode": "tag", "conflict_action": action})
    manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
    assert manager.status()["phase"] == "done", manager.status()
    assert manager.status()["total"] == 3, manager.status()
    assert manager.status()["failed"] == 0
    for name in ["a", "b", "c"]:
        assert (old / (name + ".txt")).read_bytes() == (new / (name + ".txt")).read_bytes()


@pytest.mark.parametrize("caption", ["A cat is sitting near a window.", "cat, window\n\nA cat is sitting near a window."])
def test_old_and_new_tag_merge_preserve_natural_and_mixed_caption(tmp_path, monkeypatch, caption):
    monkeypatch.setitem(available_interrogators, "wd14-convnextv2-v2", TagModel())
    monkeypatch.setattr(jobs, "interrogator_assets_ready", lambda *args: True)
    monkeypatch.setattr(jobs, "describe_interrogator_asset_status", lambda *args: (True, "fake assets ready"))
    monkeypatch.setattr(model_fetch, "interrogator_assets_ready", lambda *args: True)
    Image.new("RGB", (16, 16)).save(tmp_path / "a.png")
    target = tmp_path / "a.txt"
    target.write_text(caption, encoding="utf-8")
    tagger_progress.reset_idle()
    jobs.run_interrogate_job(TaggerInterrogateRequest(path=str(tmp_path), batch_output_action_on_conflict="append"))
    assert tagger_progress.get()["phase"] == "error"
    assert target.read_text(encoding="utf-8") == caption
    manager = CaptionJobManager(NoVision())
    manager.start({"path": str(tmp_path), "mode": "tag", "conflict_action": "append"})
    manager._thread.join(timeout=5)
    assert manager.status()["failed"] == 1
    assert target.read_text(encoding="utf-8") == caption


def test_legacy_tag_conflict_preserves_external_edit_and_unloads_model(tmp_path, monkeypatch, capsys):
    target = tmp_path / "a.txt"
    target.write_text("old_tag", encoding="utf-8")
    Image.new("RGB", (16, 16)).save(tmp_path / "a.png")

    class EditingModel(TagModel):
        unloaded = False

        def interrogate(self, image):
            target.write_text("user external edit", encoding="utf-8")
            return super().interrogate(image)

        def unload(self):
            self.unloaded = True

    model = EditingModel()
    monkeypatch.setitem(available_interrogators, "wd14-convnextv2-v2", model)
    monkeypatch.setattr(jobs, "interrogator_assets_ready", lambda *args: True)
    monkeypatch.setattr(jobs, "describe_interrogator_asset_status", lambda *args: (True, "fake assets ready"))
    tagger_progress.reset_idle()
    jobs.run_interrogate_job(TaggerInterrogateRequest(path=str(tmp_path), batch_output_action_on_conflict="copy"))
    assert tagger_progress.get()["phase"] == "error"
    assert model.unloaded
    assert target.read_text() == "user external edit"
    assert str(tmp_path) not in capsys.readouterr().out


def test_native_tag_generation_registers_source_and_editor_can_batch(tmp_path, monkeypatch, caption_store):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mikazuki.dataset_editor import router
    monkeypatch.setitem(available_interrogators, "wd14-convnextv2-v2", TagModel())
    monkeypatch.setattr(jobs, "interrogator_assets_ready", lambda *args: True)
    monkeypatch.setattr(jobs, "describe_interrogator_asset_status", lambda *args: (True, "fake assets ready"))
    Image.new("RGB", (16, 16)).save(tmp_path / "a.png")
    tagger_progress.reset_idle()
    jobs.run_interrogate_job(TaggerInterrogateRequest(path=str(tmp_path), batch_output_action_on_conflict="copy"))
    assert tagger_progress.get()["phase"] == "done"
    assert caption_store.find_format(tmp_path / "a.txt", caption_sha256(tmp_path / "a.txt")) == "tag"
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        scanned = client.post("/api/dataset-editor/scan", json={"path": str(tmp_path)}).json()["data"]["items"][0]
        assert scanned["caption_format"] == "tag"
        assert "cat" in scanned["tags"]
        assert client.post("/api/dataset-editor/batch", json={"root": str(tmp_path), "images": ["a.png"], "append": ["grass"]}).status_code == 200


def test_native_tag_provenance_failure_compensates_caption(tmp_path, monkeypatch, caption_store):
    import sqlite3
    monkeypatch.setitem(available_interrogators, "wd14-convnextv2-v2", TagModel())
    monkeypatch.setattr(jobs, "interrogator_assets_ready", lambda *args: True)
    monkeypatch.setattr(jobs, "describe_interrogator_asset_status", lambda *args: (True, "fake assets ready"))
    Image.new("RGB", (16, 16)).save(tmp_path / "a.png")
    target = tmp_path / "a.txt"
    original = b"original\r\n"
    target.write_bytes(original)
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("fixture provenance offline")
    monkeypatch.setattr(caption_store, "remember_format", fail)
    tagger_progress.reset_idle()
    jobs.run_interrogate_job(TaggerInterrogateRequest(path=str(tmp_path), batch_output_action_on_conflict="copy"))
    assert tagger_progress.get()["phase"] == "error"
    assert target.read_bytes() == original
    assert caption_store.get_write_intent(target) is None


def test_native_tag_rechecks_confirmed_format_after_inference(tmp_path, monkeypatch, caption_store):
    Image.new("RGB", (16, 16)).save(tmp_path / "a.png")
    target = tmp_path / "a.txt"
    target.write_bytes(b"cat")
    caption_store.remember_format(target, caption_sha256(target), "tag")
    class FormatChangingModel(TagModel):
        def interrogate(self, image):
            caption_store.remember_format(target, caption_sha256(target), "natural")
            return super().interrogate(image)
    monkeypatch.setitem(available_interrogators, "wd14-convnextv2-v2", FormatChangingModel())
    monkeypatch.setattr(jobs, "interrogator_assets_ready", lambda *args: True)
    monkeypatch.setattr(jobs, "describe_interrogator_asset_status", lambda *args: (True, "fake assets ready"))
    tagger_progress.reset_idle()
    jobs.run_interrogate_job(TaggerInterrogateRequest(path=str(tmp_path), batch_output_action_on_conflict="append"))
    assert tagger_progress.get()["phase"] == "error"
    assert target.read_bytes() == b"cat"
    assert caption_store.find_format(target, caption_sha256(target)) == "natural"

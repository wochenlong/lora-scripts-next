import copy

import pytest
from PIL import Image

from mikazuki.app.models import TaggerInterrogateRequest
from mikazuki.tagger import jobs, model_fetch
from mikazuki.tagger.caption_job import CaptionJobManager
from mikazuki.tagger.interrogator import available_interrogators
from mikazuki.tagger.progress import tagger_progress


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
def test_new_tag_mode_matches_legacy_files_byte_for_byte(tmp_path, monkeypatch, action):
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
        (root / "b.txt").write_text("", encoding="utf-8")
    tagger_progress.reset_idle()
    request = TaggerInterrogateRequest(path=str(old), batch_output_action_on_conflict=action, additional_tags="extra", add_rating_tag=True, add_model_tag=True)
    jobs.run_interrogate_job(request)
    assert tagger_progress.get()["phase"] == "done"
    manager = CaptionJobManager(NoVision())
    manager.start({**request.dict(), "path": str(new), "mode": "tag", "conflict_action": action})
    manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
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

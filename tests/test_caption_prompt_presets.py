import json

import pytest

from mikazuki.llm.prompt_presets import list_presets, save_presets, save_settings, settings, save_document, document_revision
from mikazuki.llm.config import LLMContractError


def _preset(identifier="caption-zh"):
    return {
        "id": identifier,
        "kind": "caption_prompt",
        "name": "中文描述",
        "template": "请用{{language}}描述可见事实。",
        "system_prompt": "不要臆测。",
        "output_format": "plain_text",
        "language": "zh-CN",
        "max_length": 240,
        "model_capabilities": ["vision", "caption"],
    }


def test_caption_presets_are_stored_as_typed_user_data(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path / "user_data"))
    saved = save_presets([_preset()])
    assert saved[0]["kind"] == "caption_prompt"
    assert saved[0]["revision"]
    assert list_presets()[0]["id"] == "caption-zh"
    assert json.loads((tmp_path / "user_data" / "presets" / "caption-zh.json").read_text(encoding="utf-8"))["kind"] == "caption_prompt"


def test_caption_preset_settings_reference_existing_preset(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path / "user_data"))
    save_presets([_preset()])
    assert save_settings("caption-zh")["default_caption_preset_id"] == "caption-zh"
    assert settings()["default_caption_preset_id"] == "caption-zh"


def test_caption_preset_rejects_training_kind_and_unknown_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path / "user_data"))
    with pytest.raises(LLMContractError):
        save_presets([{**_preset(), "kind": "training"}])
    with pytest.raises(LLMContractError):
        save_presets([{**_preset(), "template": "{{secret}}"}])


def test_caption_preset_save_removes_deleted_caption_files(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path / "user_data"))
    save_presets([_preset(), _preset("caption-en")])
    save_presets([_preset()])
    assert [item["id"] for item in list_presets()] == ["caption-zh"]


def test_caption_save_preserves_training_presets_and_unrelated_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    directory = tmp_path / "presets"
    directory.mkdir()
    training = directory / "train.json"
    training.write_text('{"kind":"training","name":"keep"}', encoding="utf-8")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text('{"theme":"dark","gui_port":6006}', encoding="utf-8")
    before = training.read_bytes()
    save_document({"presets": [_preset()], "settings": {"default_caption_preset_id": "caption-zh"}, "revision": document_revision()})
    assert training.read_bytes() == before
    assert json.loads(settings_file.read_text(encoding="utf-8"))["gui_port"] == 6006
    assert json.loads(settings_file.with_suffix(".json.bak").read_text(encoding="utf-8"))["theme"] == "dark"


def test_foreign_id_collision_and_stale_revision_do_not_mutate(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    (tmp_path / "presets").mkdir()
    foreign = tmp_path / "presets" / "caption-zh.json"
    foreign.write_text('{"kind":"training"}', encoding="utf-8")
    with pytest.raises(LLMContractError, match="collides"):
        save_presets([_preset()])
    assert foreign.read_text(encoding="utf-8") == '{"kind":"training"}'
    revision = document_revision()
    save_presets([_preset("new")])
    with pytest.raises(LLMContractError, match="revision conflict"):
        save_document({"presets": [], "revision": revision})
    assert list_presets()[0]["id"] == "new"


def test_invalid_default_reference_is_rejected_before_write(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    with pytest.raises(LLMContractError):
        save_document({"presets": [_preset()], "settings": {"default_caption_preset_id": "missing"}, "revision": document_revision()})
    assert not (tmp_path / "presets").exists()


def test_explicit_legacy_import_preserves_current_user_version(monkeypatch, tmp_path):
    from mikazuki.llm.prompt_presets import import_legacy
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    save_presets([_preset()])
    legacy = {"id": "caption-zh", "name": "旧版本", "template": "旧提示词", "language": "en"}
    imported = import_legacy([legacy, {**legacy, "id": "legacy-en"}], expected_revision=document_revision())
    assert len(imported["presets"]) == 2
    assert next(item for item in list_presets() if item["id"] == "caption-zh")["name"] == "中文描述"


def test_preset_http_conflict_and_import_confirmation(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mikazuki.llm.api import router
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path))
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        document = client.get("/api/llm/prompt-presets").json()["data"]
        assert document["presets"] == []
        response = client.put("/api/llm/prompt-presets", json={**document, "presets": [_preset()]})
        assert response.status_code == 200
        assert client.put("/api/llm/prompt-presets", json=document).status_code == 409
        assert client.post("/api/llm/prompt-presets/import-legacy", json={"confirmed": False}).status_code == 400

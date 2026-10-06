from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikazuki.app import api as legacy_api
from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.tag_translation import api as translation_api
from mikazuki.tag_translation.translation_service import TranslationManager
from mikazuki.tagger.progress import tagger_progress


def test_old_interrogate_contract_still_accepts_tag_form_and_blocks_caption_busy(tmp_path, monkeypatch):
    dispatched = []
    monkeypatch.setattr(legacy_api, "run_interrogate_job", lambda request: dispatched.append(request))
    app = FastAPI()
    app.include_router(legacy_api.router, prefix="/api")
    tagger_progress.reset_idle()
    try:
        with TestClient(app) as http:
            response = http.post("/api/interrogate", json={"path": str(tmp_path), "threshold": .4, "additional_tags": "cat", "batch_output_action_on_conflict": "copy"})
            assert response.status_code == 200
            assert response.json()["status"] == "success"
            assert len(dispatched) == 1
            assert dispatched[0].threshold == .4
            assert dispatched[0].additional_tags == "cat"
            assert tagger_progress.try_begin("captioning", "vision", "busy")
            response = http.post("/api/interrogate", json={"path": str(tmp_path)})
            assert response.status_code == 200  # Existing fail envelope is preserved.
            assert response.json()["status"] == "fail"
            assert len(dispatched) == 1
    finally:
        tagger_progress.release()
        tagger_progress.reset_idle()


def test_old_translation_api_masks_keys_and_remote_selection_keeps_shared_runtime(tmp_path, monkeypatch):
    path = tmp_path / "translation.json"
    manager = TranslationManager(path, None)
    monkeypatch.setattr(translation_api, "translation_manager", manager)
    stop = AsyncMock()
    monkeypatch.setattr(translation_api.local_model_service, "stop_runtime", stop)
    app = FastAPI()
    app.include_router(translation_api.router, prefix="/api")
    with TestClient(app) as http:
        response = http.put("/api/tag-translation/config", json={"llm_mode": "remote", "deepseek": {"api_key": "fixture-runtime-key"}})
        assert response.status_code == 200
        assert "fixture-runtime-key" not in response.text
        assert response.json()["data"]["deepseek"]["api_key"] == "********"
        assert "fixture-runtime-key" not in path.read_text(encoding="utf-8")
        assert "fixture-runtime-key" not in http.get("/api/tag-translation/config").text
        stop.assert_not_called()


def test_old_translation_can_enable_fallback_using_shared_ready_text_model(tmp_path, monkeypatch):
    path = tmp_path / "translation.json"
    manager = TranslationManager(path, None)
    monkeypatch.setattr(translation_api, "translation_manager", manager)
    monkeypatch.setattr(translation_api.local_model_service, "status", lambda: {"installed": False, "state": "missing"})
    shared = UnifiedConfigStore(path)
    shared.save({"profiles": [{"id": "local", "name": "Shared Qwen", "source": "managed-local",
                               "endpoint": "http://127.0.0.1:8080/v1/chat/completions", "model": "qwen",
                               "capabilities": ["text", "vision"], "languages": ["zh-CN"]}]})
    app = FastAPI()
    app.include_router(translation_api.router, prefix="/api")
    with TestClient(app) as http:
        response = http.put("/api/tag-translation/config", json={"llm_mode": "local"})
        assert response.status_code == 200
        assert response.json()["data"]["local"]["enabled"] is True

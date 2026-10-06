import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from mikazuki.llm.contracts import LLMProfile, LLMRouteError
from mikazuki.tagger import caption_api
from mikazuki.tagger.caption_job import CaptionJobManager
from mikazuki.tagger.progress import tagger_progress


class Service:
    def __init__(self):
        self.calls = []
        self.profile = LLMProfile(
            id="remote", name="Remote", endpoint="https://example.test/v1/chat/completions",
            model="vision", source="remote", capabilities=("text", "vision"), languages=("zh-CN",),
        )

    def resolve(self, capability, **kwargs):
        if kwargs.get("profile_id") == "text-only":
            raise LLMRouteError("vision is required", "llm_capability_vision_required")
        return self.profile

    async def complete_vision(self, image_path, prompt, **kwargs):
        self.calls.append((Path(image_path).name, kwargs))
        return self.profile, {"choices": [{"finish_reason": "stop"}]}, '{"caption":"一只猫坐在窗边。","language":"zh-CN"}', {"bytes": 64}


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    service = Service()
    manager = CaptionJobManager(service)
    monkeypatch.setattr(caption_api, "llm_service", service)
    monkeypatch.setattr(caption_api, "caption_job_manager", manager)
    app = FastAPI()
    app.include_router(caption_api.router, prefix="/api")
    image = tmp_path / "a.png"
    Image.new("RGB", (16, 16)).save(image)
    tagger_progress.reset_idle()
    yield TestClient(app), image, manager, service
    if manager._thread:
        manager.cancel()
        manager._thread.join(timeout=5)
    tagger_progress.reset_idle()


def test_preview_never_writes_caption_and_fallback_defaults_off(api_client):
    client, image, _manager, service = api_client
    response = client.post("/api/tagger/jobs/preview", json={
        "path": str(image.parent), "image_path": str(image), "mode": "natural", "profile_id": "remote",
    })
    assert response.status_code == 200
    assert response.json()["data"]["profile_id"] == "remote"
    assert not image.with_suffix(".txt").exists()
    assert service.calls[0][1]["allow_local_fallback"] is False


def test_job_real_api_writes_and_exposes_report(api_client):
    client, image, manager, _service = api_client
    response = client.post("/api/tagger/jobs", json={"path": str(image.parent), "mode": "natural", "profile_id": "remote"})
    assert response.status_code == 200
    job_id = response.json()["data"]["job_id"]
    manager._thread.join(timeout=5)
    detail = client.get(f"/api/tagger/jobs/{job_id}").json()["data"]
    assert detail["succeeded"] == 1
    assert detail["report"]["items"][0]["after_hash"]
    assert image.with_suffix(".txt").read_text(encoding="utf-8").strip() == "一只猫坐在窗边。"


def test_text_only_profile_is_rejected_before_start(api_client):
    client, image, manager, service = api_client
    response = client.post("/api/tagger/jobs", json={"path": str(image.parent), "profile_id": "text-only"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "llm_capability_vision_required"
    assert not manager.is_busy()
    assert not service.calls


def test_legacy_tagger_reservation_blocks_new_caption_job(api_client):
    client, image, manager, service = api_client
    assert tagger_progress.try_begin("tagging", "wd14", "busy")
    response = client.post("/api/tagger/jobs", json={"path": str(image.parent)})
    assert response.status_code == 409
    assert not manager.is_busy()
    assert not service.calls


def test_preview_rejects_truncated_response_even_if_json_is_parseable(api_client, monkeypatch):
    client, image, _manager, service = api_client

    async def truncated(*args, **kwargs):
        return service.profile, {"choices": [{"finish_reason": "length"}]}, '{"caption":"一只猫。","language":"zh-CN"}', {}

    monkeypatch.setattr(service, "complete_vision", truncated)
    response = client.post("/api/tagger/jobs/preview", json={"path": str(image.parent), "image_path": str(image)})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "llm_invalid_response"
    assert not image.with_suffix(".txt").exists()


def test_preview_error_never_echoes_private_paths_or_provider_text(api_client, monkeypatch):
    client, image, _manager, service = api_client

    async def failed(*args, **kwargs):
        raise RuntimeError("private provider response " + str(image))

    monkeypatch.setattr(service, "complete_vision", failed)
    response = client.post("/api/tagger/jobs/preview", json={"path": str(image.parent), "image_path": str(image)})
    assert response.status_code == 502
    assert str(image) not in response.text
    assert "private provider response" not in response.text
    assert not image.with_suffix(".txt").exists()

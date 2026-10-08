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
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path / "user_data"))
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


def test_tag_preview_and_batch_use_same_generation_parameters_without_llm(api_client, monkeypatch):
    client, image, manager, service = api_client
    calls = []
    monkeypatch.setattr(manager, "_prepare_tag_model", lambda payload: None)

    def generate(path, payload):
        calls.append((path, payload.copy()))
        return ["cat", "window"]

    def forbidden(*args, **kwargs):
        raise AssertionError("Tag mode must not use LLM configuration")

    monkeypatch.setattr(manager, "_generate_tags", generate)
    monkeypatch.setattr(service, "resolve", forbidden)
    monkeypatch.setattr(service, "config", forbidden, raising=False)
    payload = {"path": str(image.parent), "mode": "tag", "model_id": "wd14-convnextv2-v2", "runtime": "local", "threshold": .45, "additional_tags": "example"}
    original = b"old caption\r\n"
    image.with_suffix(".txt").write_bytes(original)
    preview = client.post("/api/tagger/jobs/preview", json={**payload, "image_path": str(image)})
    assert preview.status_code == 200, preview.text
    assert preview.json()["data"]["tags"] == ["cat", "window"]
    assert preview.json()["data"]["language"] == "native"
    assert image.with_suffix(".txt").read_bytes() == original
    batch = client.post("/api/tagger/jobs", json={**payload, "conflict_action": "copy"})
    assert batch.status_code == 200, batch.text
    manager._thread.join(timeout=5)
    assert manager.status()["succeeded"] == 1
    assert image.with_suffix(".txt").read_text(encoding="utf-8").strip() == preview.json()["data"]["caption"]
    assert calls[0][1]["threshold"] == calls[1][1]["threshold"] == .45
    assert calls[0][1]["additional_tags"] == calls[1][1]["additional_tags"] == "example"
    assert not service.calls
    assert "max_tokens" not in manager.status()["snapshot"]
    assert "prompt" not in manager.status()["snapshot"]


@pytest.mark.parametrize("parameters", [{"prompt": "bad"}, {"max_tokens": 300}, {"language": "en"}, {"profile_id": "remote"}])
def test_tag_requests_reject_caption_parameters_in_preview_and_batch(api_client, parameters):
    client, image, manager, service = api_client
    for url, extra in [("/api/tagger/jobs", {}), ("/api/tagger/jobs/preview", {"image_path": str(image)})]:
        result = client.post(url, json={"path": str(image.parent), "mode": "tag", **extra, **parameters})
        assert result.status_code == 400
        assert result.json()["detail"]["code"] == "tagger_parameter_unsupported"
    assert not manager.is_busy()
    assert not service.calls


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


def test_persisted_history_and_report_routes_exclude_private_recovery_data(api_client):
    from mikazuki.tagger.caption_store import CaptionJobStore
    client, image, manager, _service = api_client
    manager.job_store = CaptionJobStore(image.parent / "reports.sqlite3")
    first_id = client.post("/api/tagger/jobs", json={"path": str(image.parent)}).json()["data"]["job_id"]
    manager._thread.join(timeout=5)
    client.post("/api/tagger/jobs", json={"path": str(image.parent)})
    manager._thread.join(timeout=5)
    history = client.get("/api/tagger/jobs/history")
    assert history.status_code == 200
    assert len(history.json()["data"]["jobs"]) == 2
    report = client.get(f"/api/tagger/jobs/{first_id}/report")
    assert report.status_code == 200
    assert report.json()["data"]["report"]["items"][0]["before_hash"] is None
    assert report.json()["data"]["report"]["items"][0]["image_sha256"]
    assert str(image.parent) not in report.text
    assert "expected_hashes" not in report.text
    assert "_prompt_frozen" not in report.text
    assert client.get(f"/api/tagger/jobs/{first_id}").status_code == 200


def test_prompt_id_resolves_preset_and_does_not_transmit_filename(api_client, monkeypatch):
    client, image, manager, service = api_client
    monkeypatch.setattr(service, "config", lambda **kwargs: {"prompt_presets": [
        {"id": "short", "name": "简洁", "template": "Use {{language}} for {{image_name}}", "language": "zh-CN"}
    ]}, raising=False)
    original = service.complete_vision

    async def check_prompt(image_path, prompt, **kwargs):
        assert prompt == "Use zh-CN for image"
        assert image.name not in prompt
        return await original(image_path, prompt, **kwargs)

    monkeypatch.setattr(service, "complete_vision", check_prompt)
    response = client.post("/api/tagger/jobs", json={"path": str(image.parent), "prompt_id": "short"})
    assert response.status_code == 200
    manager._thread.join(timeout=5)
    assert manager.status()["succeeded"] == 1
    assert manager.status()["snapshot"]["prompt_id"] == "short"
    assert client.post("/api/tagger/jobs/preview", json={"path": str(image.parent), "image_path": str(image), "prompt_id": "short"}).status_code == 200


def test_unknown_preset_rejected_before_job_or_request(api_client, monkeypatch):
    client, image, manager, service = api_client
    monkeypatch.setattr(service, "config", lambda **kwargs: {"prompt_presets": []}, raising=False)
    response = client.post("/api/tagger/jobs", json={"path": str(image.parent), "prompt_id": "missing"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "caption_prompt_invalid"
    assert not manager.is_busy()
    assert not service.calls


@pytest.mark.parametrize("fields", [{"threshold": 0.9}, {"replace_underscore": True}, {"interrogator_model": "wd-vit-v3"}, {"conflict_action": "append"}, {"layout": "tags_only"}])
def test_natural_requests_reject_tag_or_mixed_parameters_before_execution(api_client, fields):
    client, image, manager, service = api_client
    for url, extra in [("/api/tagger/jobs", {}), ("/api/tagger/jobs/preview", {"image_path": str(image)})]:
        response = client.post(url, json={"path": str(image.parent), "mode": "natural", **extra, **fields})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "tagger_parameter_unsupported"
    assert not manager.is_busy()
    assert not service.calls


def test_natural_default_skips_existing_caption(api_client):
    client, image, manager, service = api_client
    image.with_suffix(".txt").write_bytes(b"keep original")
    assert client.post("/api/tagger/jobs", json={"path": str(image.parent)}).status_code == 200
    manager._thread.join(timeout=5)
    assert manager.status()["skipped"] == 1
    assert not service.calls
    assert image.with_suffix(".txt").read_bytes() == b"keep original"


def test_forged_model_runtime_rejected_and_valid_parameters_frozen(api_client, monkeypatch):
    client, image, manager, service = api_client
    monkeypatch.setattr(service, "config", lambda **kwargs: {"profiles": [{"id": "remote", "source": "remote", "capabilities": ["vision"], "enabled": True}]}, raising=False)
    payload = {"path": str(image.parent), "model_id": "llm:remote", "profile_id": "remote", "runtime": "local", "max_tokens": 256, "temperature": 0.2}
    assert client.post("/api/tagger/jobs", json=payload).status_code == 400
    assert not service.calls
    response = client.post("/api/tagger/jobs", json={**payload, "runtime": "api"})
    assert response.status_code == 200
    manager._thread.join(timeout=5)
    assert service.calls[-1][1]["max_tokens"] == 256
    assert service.calls[-1][1]["temperature"] == 0.2
    assert manager.status()["snapshot"]["max_tokens"] == 256
    assert manager.status()["snapshot"]["model_id"] == "llm:remote"


def test_user_data_preset_freezes_system_prompt_for_preview_and_batch(api_client, monkeypatch):
    from mikazuki.llm.prompt_presets import save_presets
    client, image, manager, service = api_client
    monkeypatch.setattr(service, "config", lambda **kwargs: {"prompt_presets": []}, raising=False)
    save_presets([{"id": "user", "kind": "caption_prompt", "name": "用户", "template": "Use {{language}}", "system_prompt": "Only visible facts", "language": "zh-CN"}])
    preview = client.post("/api/tagger/jobs/preview", json={"path": str(image.parent), "image_path": str(image), "prompt_id": "user"})
    assert preview.status_code == 200
    assert service.calls[-1][1]["system_prompt"] == "Only visible facts"
    response = client.post("/api/tagger/jobs", json={"path": str(image.parent), "prompt_id": "user"})
    assert response.status_code == 200
    manager._thread.join(timeout=5)
    assert service.calls[-1][1]["system_prompt"] == "Only visible facts"
    assert manager._request["system_prompt"] == "Only visible facts"
    assert manager._request["preset_revision"]


def test_openapi_does_not_advertise_unsupported_combined_output(api_client):
    client, *_ = api_client
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("CaptionJobRequest", "CaptionPreviewRequest"):
        assert schemas[name]["properties"]["mode"]["enum"] == ["natural", "tag"]
        assert schemas[name]["properties"]["layout"]["enum"] == ["tags_only", "caption_only"]


def test_combined_preview_is_rejected_by_issue_409_contract(api_client):
    client, image, _manager, _service = api_client
    response = client.post("/api/tagger/jobs/preview", json={"path": str(image.parent), "image_path": str(image), "mode": "combined", "layout": "caption_then_tags"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "caption_combined_unsupported"
    assert not image.with_suffix(".txt").exists()
    assert not tagger_progress.is_busy()


def test_preview_obeys_shared_tagger_busy_guard(api_client):
    client, image, _manager, service = api_client
    assert tagger_progress.try_begin("tagging", "wd14", "busy")
    response = client.post("/api/tagger/jobs/preview", json={"path": str(image.parent), "image_path": str(image)})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "tagger_busy"
    assert not service.calls


def test_preview_cancel_aborts_provider_and_releases_reservation(api_client, monkeypatch):
    client, image, _manager, service = api_client
    aborted = []

    async def waiting(*args, **kwargs):
        tagger_progress.request_cancel()
        try:
            await asyncio.sleep(60)
        finally:
            aborted.append(True)

    monkeypatch.setattr(service, "complete_vision", waiting)
    response = client.post("/api/tagger/jobs/preview", json={"path": str(image.parent), "image_path": str(image)})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "caption_cancelled"
    assert aborted == [True]
    assert not tagger_progress.is_busy()
    assert not image.with_suffix(".txt").exists()


def test_tag_preview_cancel_holds_reservation_until_native_inference_finishes(api_client, monkeypatch):
    import threading
    client, image, manager, service = api_client
    started = threading.Event()
    finish = threading.Event()
    response = []
    monkeypatch.setattr(manager, "_prepare_tag_model", lambda payload: None)

    def generate(*args):
        started.set()
        assert finish.wait(timeout=5)
        return ["cat"]

    monkeypatch.setattr(manager, "_generate_tags", generate)
    original = b"keep original\r\n"
    image.with_suffix(".txt").write_bytes(original)
    worker = threading.Thread(target=lambda: response.append(client.post("/api/tagger/jobs/preview", json={"path": str(image.parent), "image_path": str(image), "mode": "tag"})))
    worker.start()
    try:
        assert started.wait(timeout=3)
        tagger_progress.request_cancel()
        assert tagger_progress.is_busy()
        assert not tagger_progress.try_begin("captioning", "other", "must remain locked")
        assert image.with_suffix(".txt").read_bytes() == original
    finally:
        finish.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert response[0].status_code == 409
    assert response[0].json()["detail"]["code"] == "caption_cancelled"
    assert not tagger_progress.is_busy()
    assert not service.calls
    assert image.with_suffix(".txt").read_bytes() == original


def test_preset_length_limit_is_frozen_and_excess_output_is_rejected(api_client, monkeypatch):
    client, image, manager, service = api_client
    monkeypatch.setattr(service, "config", lambda **kwargs: {"prompt_presets": [
        {"id": "tiny", "name": "Tiny", "template": "Describe {{language}}", "language": "zh-CN", "max_length": 2}
    ]}, raising=False)
    response = client.post("/api/tagger/jobs", json={"path": str(image.parent), "prompt_id": "tiny"})
    assert response.status_code == 200
    manager._thread.join(timeout=5)
    assert manager.status()["snapshot"]["max_caption_length"] == 2
    assert manager.status()["failed"] == 1
    assert not image.with_suffix(".txt").exists()
    assert service.calls[0][1]["response_schema"]["properties"]["caption"]["maxLength"] == 2

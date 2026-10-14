import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikazuki.llm.api import router
from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.llm.service import UnifiedLLMService


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = UnifiedConfigStore(tmp_path / "translation.json")
    monkeypatch.setattr("mikazuki.llm.api.llm_service", UnifiedLLMService(store))
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as http:
        yield http, store


@pytest.mark.parametrize("payload", [
    {"routes": []}, {"routes": {"caption": False}}, {"routes": {"unknown": "x"}},
    {"cache": {"caption": "false"}}, {"cache": []}, {"prompt_presets": {}},
    {"prompt_presets": [{"id": "empty"}]},
    {"prompt_presets": [{"id": "p", "name": "p", "language": "zh-CN", "template": "{{absolute_path}}"}]},
    {"profiles": [{"id": "p", "model": "m", "endpoint": "https:///v1/chat/completions"}]},
    {"profiles": [{"id": "p", "model": "m", "endpoint": "https://example.test:bad/v1/chat/completions"}]},
    {"profiles": [{"id": "p", "model": "m", "endpoint": "https://example.test/v1/chat/completions", "secret_revision": "bad"}]},
    {"profiles": [{"id": "p", "model": "m", "endpoint": "https://example.test/v1/chat/completions", "metadata": [1]}]},
])
def test_malformed_config_returns_400_without_partial_write(client, payload):
    http, store = client
    response = http.put("/api/llm/config", json={**payload, "revision": store.load()["revision"]})
    assert response.status_code == 400
    assert not store.path.exists()


def test_zero_config_and_prompt_preset_round_trip_without_download(client):
    http, store = client
    assert http.get("/api/llm/config").json()["data"]["profiles"] == []
    preset = {"id": "zh", "name": "中文", "template": "Describe in {{language}}", "language": "zh-CN"}
    response = http.put("/api/llm/config", json={"prompt_presets": [preset], "revision": http.get("/api/llm/config").json()["data"]["revision"]})
    assert response.status_code == 200
    saved = http.get("/api/llm/config").json()["data"]["prompt_presets"][0]
    assert all(saved[key] == value for key, value in preset.items())
    assert saved["max_length"] == 2000
    assert len(saved["revision"]) == 24
    assert sorted(item.name for item in store.path.parent.iterdir()) == ["translation.json"]


def test_connection_test_without_capability_discovers_text_and_vision(client, monkeypatch):
    import json
    http, store = client
    store.save({"profiles": [{"id": "model", "name": "Model", "source": "remote",
                "model": "model", "endpoint": "http://127.0.0.1:8080/v1/chat/completions",
                "capabilities": ["text"], "languages": ["en", "zh-CN"]}]})
    calls = []

    async def completion(profile, payload, **kwargs):
        calls.append(payload)
        response = ({"red_shape": "square", "blue_shape": "circle", "green_shape": "triangle"}
                    if isinstance(payload["messages"][-1]["content"], list)
                    else {"translation": "红色圆形在蓝色方块的左侧。", "language": "zh-CN"})
        return {"choices": [{"finish_reason": "stop"}]}, json.dumps(response, ensure_ascii=False)

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", completion)
    response = http.post("/api/llm/connection-test", json={"profile_id": "model"})
    assert response.status_code == 200
    assert response.json()["data"]["verified_capabilities"] == ["text", "vision"]
    assert len(calls) == 2
    assert http.get("/api/llm/profiles").json()["data"]["profiles"][0]["ready"] is True


@pytest.mark.parametrize("contents", [
    "not json",
    '{"llm":{"profiles":false}}',
    '{"llm":{"profiles":[],"routes":[]}}',
    '{"llm":{"profiles":[],"cache":false}}',
    '{"llm":{"profiles":[],"prompt_presets":false}}',
])
def test_corrupt_configuration_returns_actionable_error_without_overwriting(client, contents):
    http, store = client
    store.path.write_text(contents, encoding="utf-8")
    for endpoint in ["config", "profiles"]:
        response = http.get("/api/llm/" + endpoint)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "llm_config_invalid"
        assert str(store.path) not in response.text
    assert store.path.read_text(encoding="utf-8") == contents


def test_preset_length_limit_changes_server_computed_revision(client):
    http, _store = client
    preset = {"id": "short", "name": "Short", "template": "Describe {{language}}", "language": "zh-CN", "max_length": 20}
    first = http.put("/api/llm/config", json={"prompt_presets": [preset], "revision": http.get("/api/llm/config").json()["data"]["revision"]}).json()["data"]["prompt_presets"][0]
    second = http.put("/api/llm/config", json={"prompt_presets": [{**preset, "max_length": 40, "revision": "caller-supplied"}], "revision": http.get("/api/llm/config").json()["data"]["revision"]}).json()["data"]["prompt_presets"][0]
    assert first["revision"] != second["revision"] != "caller-supplied"
    before = http.get("/api/llm/config").json()["data"]
    assert http.put("/api/llm/config", json={"prompt_presets": [{**preset, "max_length": False}], "revision": before["revision"]}).status_code == 400
    assert http.get("/api/llm/config").json()["data"] == before

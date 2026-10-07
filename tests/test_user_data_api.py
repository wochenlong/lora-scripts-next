import asyncio
import json
import sys

import httpx
import pytest
from fastapi import FastAPI

from mikazuki.app import user_data_api
from mikazuki.user_data import UserDataStore


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(user_data_api, "store", UserDataStore(tmp_path))
    app = FastAPI()
    app.include_router(user_data_api.router, prefix="/api")
    return app


def request(app, method, path, **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, path, **kwargs)
    return asyncio.run(run())


@pytest.fixture
def bounded_recursion():
    previous = sys.getrecursionlimit()
    sys.setrecursionlimit(300)
    try:
        yield
    finally:
        sys.setrecursionlimit(previous)


def test_settings_patch_and_conflict(app):
    first = request(app, "GET", "/api/user-data/settings").json()["data"]
    assert first["revision"] == 0
    payload = {"revision": 0, "patch": {"engine_prefs": {"defaultEngine": "ai-toolkit"}}}
    result = request(app, "PATCH", "/api/user-data/settings", json=payload)
    assert result.status_code == 200
    assert result.json()["data"]["engine_prefs"]["defaultEngine"] == "ai-toolkit"
    assert request(app, "PATCH", "/api/user-data/settings", json=payload).status_code == 409


def test_preset_crud_list_contract(app):
    endpoint = "/api/user-data/presets"
    assert request(app, "GET", endpoint).json()["data"] == {"presets": []}
    created = request(app, "POST", endpoint, json={
        "name": "Contract", "train_type": "anima", "config": {"max_train_steps": 100},
    })
    assert created.status_code == 200
    preset = created.json()["data"]
    assert request(app, "GET", endpoint + "?train_type=anima").json()["data"]["presets"] == [preset]
    assert request(app, "GET", endpoint + "?train_type=sdxl").json()["data"]["presets"] == []
    item_url = endpoint + "/" + preset["id"]
    assert request(app, "PATCH", item_url, json={"name": "Updated"}).json()["data"]["name"] == "Updated"
    assert request(app, "DELETE", item_url).status_code == 200
    assert request(app, "GET", endpoint).json()["data"] == {"presets": []}


def test_archive_list_detail_contract(app, tmp_path):
    endpoint = "/api/user-data/task-archives"
    assert request(app, "GET", endpoint).json()["data"] == {"archives": []}
    config = tmp_path / "training.toml"
    config.write_text('output_name = "contract-run"\nmax_train_steps = 100\n', encoding="utf-8")
    user_data_api.store.archive_task("contract-task", {
        "backend": "anima-fast", "train_type": "anima",
    }, config)
    archives = request(app, "GET", endpoint + "?train_type=anima").json()["data"]["archives"]
    assert len(archives) == 1
    archive = archives[0]
    assert archive["id"] == "contract-task"
    assert archive["name"] == "contract-run"
    assert archive["train_type"] == "anima"
    assert archive["engine"] == "anima-fast"
    assert request(app, "GET", endpoint + "/" + archive["id"]).json()["data"] == archive
    assert archive["config"]["max_train_steps"] == 100
    assert request(app, "GET", endpoint + "?train_type=sdxl").json()["data"] == {"archives": []}


def test_settings_reject_secret_and_unknown_fields(app):
    result = request(app, "PATCH", "/api/user-data/settings",
                     json={"revision": 0, "patch": {"api_key": "sensitive-value"}})
    assert result.status_code == 422
    assert "sensitive-value" not in result.text


def test_auth_is_write_only_and_never_cached(app):
    result = request(app, "PUT", "/api/user-data/auth/provider",
                     json={"revision": 0, "secret": "sensitive-value"})
    assert result.status_code == 200
    assert "sensitive-value" not in result.text
    assert result.headers["cache-control"] == "no-store"
    assert request(app, "GET", "/api/user-data/auth").json()["data"]["providers"]["provider"]["configured"]
    assert "sensitive-value" not in request(app, "GET", "/api/user-data/auth").text


def test_browser_cross_site_writes_rejected(app):
    result = request(app, "PATCH", "/api/user-data/settings",
                     headers={"sec-fetch-site": "cross-site"},
                     json={"revision": 0, "patch": {}})
    assert result.status_code == 403


def test_oversized_body_rejected(app):
    result = request(app, "PATCH", "/api/user-data/settings",
                     content=b"x" * (1024 * 1024 + 1),
                     headers={"content-type": "application/json"})
    assert result.status_code == 413


def test_corrupt_file_read_reports_failure_without_data(app, tmp_path):
    (tmp_path / "settings.json").write_text("broken")
    result = request(app, "GET", "/api/user-data/settings")
    assert result.status_code == 422
    assert result.json()["status"] == "fail"


@pytest.mark.parametrize("endpoint,method,field", [
    ("settings", "PATCH", "patch"),
    ("auth/provider", "PUT", "secret"),
])
@pytest.mark.parametrize("depth", [600, 1200])
def test_nested_json_is_sanitized_and_preserves_files(
    app, tmp_path, caplog, bounded_recursion, endpoint, method, field, depth,
):
    store = user_data_api.store
    store.patch_settings({"paths": {"datasets": "first"}}, 0)
    store.patch_settings({"paths": {"datasets": "second"}}, 1)
    store.set_credential("provider", "existing-secret", 0)
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}
    nested = "[" * depth + '"sensitive-value"' + "]" * depth
    value = '{"paths":{"datasets":' + nested + "}}" if field == "patch" else nested
    body = ('{"revision":' + ("2" if field == "patch" else "1")
            + ',"' + field + '":' + value + "}").encode()
    assert len(body) < 3072
    result = request(app, method, "/api/user-data/" + endpoint, content=body,
                     headers={"content-type": "application/json"})
    assert result.status_code == 422
    assert result.json()["data"] is None
    assert "sensitive-value" not in result.text + caplog.text
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == before


@pytest.mark.parametrize("endpoint,method,payload", [
    ("settings", "PATCH", {"revision": 1, "patch": {"paths": {"datasets": "sensitive-value\ud800"}}}),
    ("settings", "PATCH", {"revision": 1, "patch": {"paths": {"models": {"sensitive-value\udfff": "path"}}}}),
    ("auth/provider", "PUT", {"revision": 1, "secret": "sensitive-value\udfff"}),
])
def test_surrogate_request_is_sanitized_and_preserves_files(
    app, tmp_path, caplog, endpoint, method, payload,
):
    user_data_api.store.patch_settings({"paths": {"datasets": "existing"}}, 0)
    user_data_api.store.set_credential("provider", "existing-secret", 0)
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}
    result = request(app, method, "/api/user-data/" + endpoint,
                     content=json.dumps(payload).encode("ascii"),
                     headers={"content-type": "application/json"})
    assert result.status_code == 422
    assert result.json()["data"] is None
    assert "sensitive-value" not in result.text + caplog.text
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == before


@pytest.mark.parametrize("endpoint,raw", [
    ("settings", b"[" * 1200 + b'"sensitive-value"' + b"]" * 1200),
    ("auth", b"[" * 1200 + b'"sensitive-value"' + b"]" * 1200),
    ("settings", b'{"paths":{"datasets":"sensitive-value\\ud800"}}'),
    ("auth", b'{"providers":{"provider":"sensitive-value\\udfff"}}'),
    ("auth", b'{"schema_version":true,"providers":{"provider":"sensitive-value"}}'),
    ("auth", b'{"schema_version":1.0,"providers":{"provider":"sensitive-value"}}'),
])
def test_invalid_file_is_sanitized_and_preserved(
    app, tmp_path, caplog, bounded_recursion, endpoint, raw,
):
    path = tmp_path / (endpoint + ".json")
    path.write_bytes(raw)
    result = request(app, "GET", "/api/user-data/" + endpoint)
    assert result.status_code == 422
    assert result.json()["data"] is None
    assert "sensitive-value" not in result.text + caplog.text
    assert path.read_bytes() == raw

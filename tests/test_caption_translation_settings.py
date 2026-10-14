"""自然语言翻译参数的配置兼容性和 HTTP 保存契约。"""
from __future__ import annotations

import copy
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


SETTINGS_ENDPOINT = "/api/llm/caption-translation/settings"
DEFAULT_SETTINGS = {"concurrency": 3, "max_tokens": 2048, "temperature": 0.7}
CHANGED_SETTINGS = {"concurrency": 5, "max_tokens": 4096, "temperature": 0.75}


@pytest.fixture
def isolated_environment(tmp_path, monkeypatch):
    """在导入运行时前隔离本文件的存储、插件目录和模型缓存。"""
    for name, directory in {
        "MIKAZUKI_TAG_TRANSLATION_ROOT": "translation-runtime",
        "MIKAZUKI_USER_DATA_ROOT": "user-data",
        "MIKAZUKI_PLUGIN_MARKETPLACE_ROOT": "plugin-marketplace",
        "MIKAZUKI_AGENT_WORKSPACE_ROOT": "workspaces",
        "HF_HOME": "hf-cache",
        "MODELSCOPE_CACHE": "modelscope-cache",
    }.items():
        monkeypatch.setenv(name, str(tmp_path / directory))
    monkeypatch.setenv("MIKAZUKI_MARKETPLACE_CATALOG", str(tmp_path / "missing-catalog.json"))
    for name in (
        "MIKAZUKI_MARKETPLACE_TRUST",
        "MIKAZUKI_MARKETPLACE_CATALOG_URL",
        "MIKAZUKI_MARKETPLACE_PACKAGE_ROOT",
        "MIKAZUKI_MARKETPLACE_PACKAGE_MIRROR",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("MIKAZUKI_PORT", "28000")
    monkeypatch.setenv("MIKAZUKI_OPEN_BROWSER", "0")


@pytest.fixture
def store(tmp_path, isolated_environment):
    from mikazuki.llm.config import UnifiedConfigStore

    return UnifiedConfigStore(tmp_path / "translation.json")


@pytest.fixture
def client(store, monkeypatch):
    from mikazuki.llm import api
    from mikazuki.llm.service import UnifiedLLMService

    async def unexpected_provider_request(*_args, **_kwargs):
        pytest.fail("设置读写不应向模型供应商发送请求")

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", unexpected_provider_request)
    monkeypatch.setattr(api, "llm_service", UnifiedLLMService(store))
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    with TestClient(app) as http:
        yield http, store


def _profile(profile_id="text"):
    return {
        "id": profile_id,
        "name": "隔离测试接口 " + profile_id,
        "endpoint": "https://example.test/v1/chat/completions",
        "model": "fake-model",
        "source": "remote",
        "capabilities": ["text", "vision"],
        "languages": ["zh-CN", "en"],
        "api_key": "fake-key-" + profile_id,
        "metadata": {"translation_system_prompt": "只翻译标签", "reasoning_effort": "disabled"},
    }


def _data(response):
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert body["message"] is None
    return body["data"]


def test_default_settings_have_shared_revision_without_creating_configuration(client):
    http, config_store = client
    data = _data(http.get(SETTINGS_ENDPOINT))
    assert set(data) == {"settings", "revision"}
    assert data["settings"] == DEFAULT_SETTINGS
    assert len(data["revision"]) == 24
    assert data["revision"] == _data(http.get("/api/llm/config"))["revision"]
    assert config_store.load()["caption_translation"] == DEFAULT_SETTINGS
    assert not config_store.path.exists()


@pytest.mark.parametrize("legacy_version", [4, 5])
def test_old_configuration_migration_supplies_defaults_without_rewriting_document(store, legacy_version):
    from mikazuki.llm.config import migrate_legacy_translation_config
    from mikazuki.llm.secrets import write_configuration

    if legacy_version == 4:
        document = {
            "version": 4,
            "active_remote_id": "text",
            "remote_profiles": [_profile()],
            "deepseek": {**_profile(), "concurrency": 17},
            "dictionary": {"enabled": False},
        }
        migration_source = document
    else:
        migration_source = {
            "version": 5,
            "profiles": [_profile()],
            "routes": {"caption": "text", "translation": "text"},
            "prompt_presets": [],
            "cache": {"caption": False, "translation": True},
            "local_fallback_enabled": False,
        }
        document = {"version": 4, "llm": migration_source, "features": {"llm": True}}
    migrated = migrate_legacy_translation_config(migration_source)
    assert migrated["version"] == 5
    assert migrated["caption_translation"] == DEFAULT_SETTINGS
    assert migrated["profiles"][0]["api_key"] == "fake-key-text"
    write_configuration(store.path, document)
    persisted_before = store.path.read_bytes()
    loaded = store.load()
    assert loaded["caption_translation"] == DEFAULT_SETTINGS
    assert loaded["profiles"][0]["api_key"] == "fake-key-text"
    assert store.path.read_bytes() == persisted_before


@pytest.mark.parametrize("settings", [
    {"concurrency": 1, "max_tokens": 128, "temperature": 0},
    {"concurrency": 8, "max_tokens": 8192, "temperature": 2},
    {"concurrency": 3, "max_tokens": 2048, "temperature": 0.125},
])
def test_save_accepts_inclusive_boundaries_and_round_trips_shared_revision(client, settings):
    http, config_store = client
    before = _data(http.get(SETTINGS_ENDPOINT))
    saved = _data(http.put(SETTINGS_ENDPOINT, json={"revision": before["revision"], "settings": settings}))
    assert set(saved) == {"settings", "revision"}
    assert saved["settings"] == settings
    assert saved["revision"] != before["revision"]
    assert _data(http.get(SETTINGS_ENDPOINT)) == saved
    shared = _data(http.get("/api/llm/config"))
    assert shared["caption_translation"] == settings
    assert shared["revision"] == saved["revision"] == config_store.load()["revision"]


INVALID_SETTINGS = [
    pytest.param(None, id="null"),
    pytest.param([], id="array"),
    pytest.param("settings", id="string"),
    pytest.param({}, id="empty"),
    pytest.param({"max_tokens": 2048, "temperature": 0}, id="missing-concurrency"),
    pytest.param({"concurrency": 3, "temperature": 0}, id="missing-max-tokens"),
    pytest.param({"concurrency": 3, "max_tokens": 2048}, id="missing-temperature"),
    pytest.param({**DEFAULT_SETTINGS, "unknown": True}, id="unknown-setting"),
    *[
        pytest.param({**DEFAULT_SETTINGS, name: value}, id=f"{name}-{label}")
        for name in ("concurrency", "max_tokens")
        for label, value in (("bool", True), ("float", 3.0), ("string", "3"), ("null", None))
    ],
    pytest.param({**DEFAULT_SETTINGS, "concurrency": 0}, id="concurrency-below-minimum"),
    pytest.param({**DEFAULT_SETTINGS, "concurrency": 9}, id="concurrency-above-maximum"),
    pytest.param({**DEFAULT_SETTINGS, "max_tokens": 127}, id="max-tokens-below-minimum"),
    pytest.param({**DEFAULT_SETTINGS, "max_tokens": 8193}, id="max-tokens-above-maximum"),
    *[
        pytest.param({**DEFAULT_SETTINGS, "temperature": value}, id="temperature-" + label)
        for label, value in (
            ("bool", False), ("string", "0"), ("null", None), ("below-minimum", -0.01),
            ("above-maximum", 2.01), ("nan", float("nan")),
            ("positive-infinity", float("inf")), ("negative-infinity", float("-inf")),
        )
    ],
]


@pytest.mark.parametrize("settings", INVALID_SETTINGS)
def test_invalid_settings_return_422_without_partial_write(client, settings):
    http, config_store = client
    config_store.save({"caption_translation": CHANGED_SETTINGS})
    before = config_store.path.read_bytes()
    snapshot = _data(http.get(SETTINGS_ENDPOINT))
    # raw JSON permits exercising NaN/Infinity before the settings validator;
    # httpx's json= encoder itself rejects these values.
    response = http.put(
        SETTINGS_ENDPOINT,
        content=json.dumps({"revision": snapshot["revision"], "settings": settings}),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert config_store.path.read_bytes() == before
    assert _data(http.get(SETTINGS_ENDPOINT)) == snapshot


@pytest.mark.parametrize("raw_body", ["null", "[]", '"settings"', "true", "3", "{"])
def test_invalid_body_returns_422_without_creating_configuration(client, raw_body):
    http, config_store = client
    response = http.put(SETTINGS_ENDPOINT, content=raw_body, headers={"content-type": "application/json"})
    assert response.status_code == 422, response.text
    assert not config_store.path.exists()


def test_body_array_cannot_be_coerced_to_settings_object(client):
    http, config_store = client
    revision = _data(http.get(SETTINGS_ENDPOINT))["revision"]
    response = http.put(SETTINGS_ENDPOINT, json=[["revision", revision], ["settings", CHANGED_SETTINGS]])
    assert response.status_code == 422, response.text
    assert not config_store.path.exists()


@pytest.mark.parametrize("payload", [
    {}, {"settings": DEFAULT_SETTINGS},
    {"settings": DEFAULT_SETTINGS, "revision": None},
    {"settings": DEFAULT_SETTINGS, "revision": True},
    {"settings": DEFAULT_SETTINGS, "revision": 1},
    {"settings": DEFAULT_SETTINGS, "revision": ""},
    {"settings": DEFAULT_SETTINGS, "revision": "outdated"},
])
def test_missing_or_invalid_revision_returns_conflict_without_write(client, payload):
    http, config_store = client
    response = http.put(SETTINGS_ENDPOINT, json=payload)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "llm_config_conflict"
    assert not config_store.path.exists()


def test_unknown_body_field_returns_422_without_write(client):
    http, config_store = client
    revision = _data(http.get(SETTINGS_ENDPOINT))["revision"]
    response = http.put(SETTINGS_ENDPOINT, json={"revision": revision, "settings": CHANGED_SETTINGS, "cache": {}})
    assert response.status_code == 422, response.text
    assert not config_store.path.exists()


def test_missing_settings_object_returns_422_without_write(client):
    http, config_store = client
    revision = _data(http.get(SETTINGS_ENDPOINT))["revision"]
    response = http.put(SETTINGS_ENDPOINT, json={"revision": revision})
    assert response.status_code == 422, response.text
    assert not config_store.path.exists()


def test_settings_and_general_configuration_use_one_compare_and_swap_revision(client):
    http, config_store = client
    stale_settings = _data(http.get(SETTINGS_ENDPOINT))
    changed_config = _data(http.put("/api/llm/config", json={
        "revision": stale_settings["revision"], "cache": {"caption": False, "translation": True},
    }))
    after_config_write = config_store.path.read_bytes()
    stale_response = http.put(SETTINGS_ENDPOINT, json={"revision": stale_settings["revision"], "settings": CHANGED_SETTINGS})
    assert stale_response.status_code == 409
    assert config_store.path.read_bytes() == after_config_write
    assert _data(http.get(SETTINGS_ENDPOINT))["revision"] == changed_config["revision"]

    saved_settings = _data(http.put(SETTINGS_ENDPOINT, json={"revision": changed_config["revision"], "settings": CHANGED_SETTINGS}))
    assert saved_settings["revision"] != changed_config["revision"]
    after_settings_write = config_store.path.read_bytes()
    stale_response = http.put("/api/llm/config", json={
        "revision": changed_config["revision"], "cache": {"caption": True, "translation": True},
    })
    assert stale_response.status_code == 409
    assert config_store.path.read_bytes() == after_settings_write
    assert config_store.load()["cache"] == {"caption": False, "translation": True}


@pytest.mark.parametrize("legacy_version", [4, 5])
def test_settings_only_save_preserves_profiles_keys_tag_parameters_and_document_sections(client, legacy_version):
    from mikazuki.llm.config import config_revision
    from mikazuki.llm.secrets import read_configuration, write_configuration

    http, config_store = client
    if legacy_version == 5:
        config_store.save({
            "profiles": [_profile(), _profile("vision")],
            "routes": {"translation": "text", "caption": "vision"},
            "cache": {"translation": False, "caption": True},
            "prompt_presets": [{"id": "en", "name": "English", "template": "Describe {{language}}", "language": "en"}],
            "local_fallback_enabled": False,
        })
        profile = config_store.load()["profiles"][0]
        config_store.record_verification("text", config_revision(profile), "text")
        document = read_configuration(config_store.path)
        document["llm"]["extension_options"] = {"keep": [1, 2, 3]}
    else:
        document = {
            "version": 4,
            "active_remote_id": "text",
            "remote_profiles": [_profile()],
            "deepseek": copy.deepcopy(_profile()),
            "local": {"enabled": False, "port": 0},
        }
    document["deepseek"].update({
        "concurrency": 17, "batch_size": 9, "max_retries": 6, "timeout_seconds": 91,
        "max_tokens": 8192, "temperature": 1.5, "system_prompt": "保留原有 Tag 翻译提示词",
    })
    document["dictionary"] = {"enabled": False, "source": "keep-dictionary"}
    document["features"] = {"llm": True, "local_dictionary": False}
    document["custom_document_section"] = {"nested": {"preserve": "原样保留"}}
    write_configuration(config_store.path, document)
    before_document = read_configuration(config_store.path)
    before_config = config_store.load()

    saved = _data(http.put(SETTINGS_ENDPOINT, json={"revision": before_config["revision"], "settings": CHANGED_SETTINGS}))
    after_document = read_configuration(config_store.path)
    for name in set(before_document) - {"llm"}:
        assert after_document[name] == before_document[name], name
    if legacy_version == 5:
        expected_llm = {**before_document["llm"], "caption_translation": CHANGED_SETTINGS}
        assert after_document["llm"] == expected_llm
    after_config = config_store.load()
    for name in ("profiles", "routes", "cache", "prompt_presets", "local_fallback_enabled"):
        assert after_config[name] == before_config[name], name
    assert after_config["caption_translation"] == saved["settings"] == CHANGED_SETTINGS
    assert after_config["profiles"][0]["api_key"] == "fake-key-text"
    assert "fake-key-text" not in config_store.path.read_text(encoding="utf-8")
    assert "fake-key-text" not in json.dumps(saved)


def test_unrelated_partial_configuration_save_keeps_translation_settings(store):
    store.save({"caption_translation": CHANGED_SETTINGS})
    before = store.load()
    after = store.save({"revision": before["revision"], "cache": {"caption": False, "translation": True}})
    assert after["caption_translation"] == CHANGED_SETTINGS
    assert after["revision"] != before["revision"]
    assert store.load()["caption_translation"] == CHANGED_SETTINGS


@pytest.mark.parametrize("legacy_version", [4, 5])
def test_explicit_zero_temperature_survives_migration_load_and_unrelated_partial_save(store, legacy_version):
    from mikazuki.llm.config import migrate_legacy_translation_config
    from mikazuki.llm.secrets import write_configuration

    zero_settings = {**DEFAULT_SETTINGS, "temperature": 0}
    migration_source = {"version": legacy_version, "caption_translation": zero_settings}
    migration_source["deepseek" if legacy_version == 4 else "profiles"] = (
        _profile() if legacy_version == 4 else [_profile()]
    )
    assert migrate_legacy_translation_config(migration_source)["caption_translation"] == zero_settings
    document = migration_source if legacy_version == 4 else {"llm": migration_source}
    write_configuration(store.path, document)
    persisted_before = store.path.read_bytes()
    before = store.load()
    assert before["caption_translation"] == zero_settings
    assert store.path.read_bytes() == persisted_before

    saved = store.save({"revision": before["revision"], "cache": {"caption": False, "translation": True}})
    assert saved["caption_translation"] == zero_settings
    assert saved["profiles"] == before["profiles"]
    assert store.load()["caption_translation"] == zero_settings


def test_legacy_null_llm_section_loads_and_saves_with_tag_settings_preserved(client):
    from mikazuki.llm.secrets import read_configuration, write_configuration

    http, config_store = client
    document = {
        "version": 4,
        "llm": None,
        "active_remote_id": "text",
        "remote_profiles": [_profile()],
        "deepseek": {**_profile(), "concurrency": 17, "batch_size": 9},
        "dictionary": {"enabled": False},
    }
    write_configuration(config_store.path, document)
    before = config_store.path.read_bytes()
    loaded = _data(http.get(SETTINGS_ENDPOINT))
    assert loaded["settings"] == DEFAULT_SETTINGS
    assert config_store.path.read_bytes() == before
    saved = _data(http.put(SETTINGS_ENDPOINT, json={"revision": loaded["revision"], "settings": CHANGED_SETTINGS}))
    assert saved["settings"] == CHANGED_SETTINGS
    assert config_store.load()["profiles"][0]["api_key"] == "fake-key-text"
    persisted = read_configuration(config_store.path)
    assert persisted["llm"]["caption_translation"] == CHANGED_SETTINGS
    for name in set(document) - {"llm"}:
        assert persisted[name] == document[name], name


@pytest.mark.parametrize("invalid_stored_settings", [
    {"concurrency": 3}, {**DEFAULT_SETTINGS, "temperature": False},
    {**DEFAULT_SETTINGS, "max_tokens": 8193},
])
def test_corrupt_stored_translation_settings_return_actionable_conflict_without_rewrite(client, invalid_stored_settings):
    http, config_store = client
    document = {"llm": {"version": 5, "profiles": [], "caption_translation": invalid_stored_settings}}
    config_store.path.write_text(json.dumps(document), encoding="utf-8")
    before = config_store.path.read_bytes()
    response = http.get(SETTINGS_ENDPOINT)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "llm_config_invalid"
    assert str(config_store.path) not in response.text
    assert config_store.path.read_bytes() == before

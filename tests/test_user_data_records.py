import json

import pytest

from mikazuki.user_data import RevisionConflict, UserDataError, UserDataStore


def test_preset_crud_rejects_credentials_and_default_delete(tmp_path):
    store = UserDataStore(tmp_path)
    created = store.save_preset("portrait", {
        "name": "Portrait",
        "train_type": "anima",
        "config": {"learning_rate": 1e-4},
    })
    assert created["id"] == "portrait"
    assert store.get_preset("portrait")["name"] == "Portrait"
    with pytest.raises(RevisionConflict):
        store.save_preset("portrait", created)
    with pytest.raises(UserDataError):
        store.save_preset("bad", {"name": "Bad", "config": {"api_key": "x"}})
    store.patch_settings({"default_presets": {"anima-fast/anima/lora": "portrait"}}, 0)
    with pytest.raises(UserDataError, match="default"):
        store.delete_preset("portrait")


def test_task_archive_contains_native_file_and_parsed_config(tmp_path):
    config = tmp_path / "train.toml"
    config.write_text('output_name = "demo"\n', encoding="utf-8")
    store = UserDataStore(tmp_path / "user_data")
    record = store.archive_task("task-1", {"backend": "anima-fast", "train_type": "anima"}, config)
    assert record["config"]["output_name"] == "demo"
    assert (store.root / "tasks" / "anima-fast").is_dir()
    assert store.get_task_archive("task-1")["task_id"] == "task-1"


def test_preset_allows_tokenizer_parameters(tmp_path):
    config = {"keep_tokens": 1, "max_token_length": 225, "t5_tokenizer_path": "tokenizer"}
    assert UserDataStore(tmp_path).save_preset("valid", {"name": "Valid", "config": config})["config"] == config


@pytest.mark.parametrize("extension,content", [
    (".yaml", "model: demo\nnested:\n  api_key: native-secret\n"),
    (".json", '{"model":"demo","nested":{"api_key":"native-secret"}}'),
])
def test_archive_sanitizes_both_configs_and_metadata(tmp_path, extension, content):
    config = tmp_path / "ui.toml"
    config.write_text('output_name = "demo"\nwandb_api_key = "ui-secret"\nkeep_tokens = 1\n')
    native = tmp_path / ("engine" + extension)
    native.write_text(content)
    store = UserDataStore(tmp_path / "data")
    result = store.archive_task("run", {
        "backend": "ai-toolkit", "engine_config_path": str(native),
        "auth": {"access_token": "metadata-secret"},
    }, config)
    assert result["config"]["keep_tokens"] == 1
    assert result["engine_config"]["model"] == "demo"
    files = list(store.root.rglob("*"))
    assert any(path.name == "engine-config" + extension for path in files)
    for path in files:
        if path.is_file():
            assert "secret" not in path.read_text()
    assert "wandb_api_key" in config.read_text()
    assert "native-secret" in native.read_text()


@pytest.mark.parametrize("missing_native", [False, True])
def test_missing_archive_source_fails_without_record(tmp_path, missing_native):
    config = tmp_path / "ui.toml"
    metadata = {"backend": "ai-toolkit"}
    if missing_native:
        config.write_text('output_name = "demo"\n')
        metadata["engine_config_path"] = str(tmp_path / "missing.yaml")
    store = UserDataStore(tmp_path / "data")
    with pytest.raises(UserDataError):
        store.archive_task("run", metadata, config)
    assert store.list_task_archives() == []


def test_missing_snapshot_prevents_task_registration(tmp_path, monkeypatch):
    import mikazuki.user_data as user_data
    from mikazuki.tasks import TaskManager
    store = UserDataStore(tmp_path / "data")
    monkeypatch.setattr(user_data, "UserDataStore", lambda: store)
    manager = TaskManager()
    with pytest.raises(UserDataError):
        manager.create_task(["unused"], {}, task_id="missing-snapshot",
                            metadata={"config_path": str(tmp_path / "missing.toml")})
    assert "missing-snapshot" not in manager.tasks
    assert "missing-snapshot" not in manager._compute_queue


def test_repeated_archives_do_not_embed_previous_snapshots(tmp_path):
    store = UserDataStore(tmp_path / "data")
    config = tmp_path / "config.toml"
    config.write_text('output_name = "' + "x" * 65536 + '"\n')
    metadata = {"backend": "anima-fast"}
    for index in range(20):
        record = store.archive_task(f"retry-{index}", metadata, config)
        assert "task_archive" not in record["metadata"]
        metadata["task_archive"] = record

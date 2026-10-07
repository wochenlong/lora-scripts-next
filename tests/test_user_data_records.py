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

"""Forward tolerance: unknown fields on disk must not break older readers (#405 hardening)."""
import json

import pytest

from mikazuki.user_data import UserDataError, UserDataStore


def _write(root, name, value):
    (root / name).write_text(json.dumps(value), encoding="utf-8")


def test_read_tolerates_unknown_fields_everywhere(tmp_path):
    _write(tmp_path, "settings.json", {
        "schema_version": 1, "revision": 3, "future_flag": True,
        "paths": {"datasets": "/data", "future_path": "/x"},
        "startup": {"gui": {"port": 28000, "future_opt": 1}, "future_service": {"port": 9999}},
        "engine_prefs": {"defaultEngine": "kohya", "future_pref": "y"},
        "tasks": {"auto_retry_max": 2, "future_task_opt": "z"},
    })
    settings = UserDataStore(root=tmp_path).read_settings()
    assert settings["paths"]["datasets"] == "/data"
    assert settings["startup"]["gui"]["port"] == 28000


def test_unknown_fields_survive_a_patch_write(tmp_path):
    _write(tmp_path, "settings.json", {
        "schema_version": 1, "revision": 0, "future_flag": True,
        "paths": {"future_path": "/x"},
    })
    store = UserDataStore(root=tmp_path)
    updated = store.patch_settings({"paths": {"datasets": "/data"}}, 0)
    assert updated["future_flag"] is True
    assert updated["paths"]["future_path"] == "/x"
    assert updated["paths"]["datasets"] == "/data"


def test_patch_rejects_unknown_fields(tmp_path):
    store = UserDataStore(root=tmp_path)
    with pytest.raises(UserDataError, match="Unsupported field"):
        store.patch_settings({"paths": {"diffsynth_chache": "/typo"}}, 0)
    with pytest.raises(UserDataError, match="Unsupported field"):
        store.patch_settings({"future_top_level": 1}, 0)
    with pytest.raises(UserDataError, match="Unsupported field"):
        store.patch_settings({"startup": {"gui2": {"port": 1}}}, 0)


def test_patch_still_rejects_wrong_types(tmp_path):
    store = UserDataStore(root=tmp_path)
    with pytest.raises(UserDataError):
        store.patch_settings({"paths": {"datasets": 42}}, 0)
    with pytest.raises(UserDataError):
        store.patch_settings({"engine_prefs": {"defaultEngine": "not-an-engine"}}, 0)


def test_schema_version_still_enforced_on_read(tmp_path):
    _write(tmp_path, "settings.json", {"schema_version": 99, "revision": 0})
    with pytest.raises(UserDataError, match="schema_version"):
        UserDataStore(root=tmp_path).read_settings()


def test_auth_tolerates_and_preserves_unknown_fields(tmp_path):
    _write(tmp_path, "auth.json", {
        "schema_version": 1, "revision": 0, "providers": {"hf": "secret"}, "future_auth_meta": {"a": 1},
    })
    store = UserDataStore(root=tmp_path)
    assert store.get_credential("hf") == "secret"
    store.set_credential("hf", "rotated", 0)
    data = json.loads((tmp_path / "auth.json").read_text(encoding="utf-8"))
    assert data["future_auth_meta"] == {"a": 1}

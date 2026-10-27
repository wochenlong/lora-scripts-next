"""DiffSynth cache directory configuration and pre-conversion space checks (#391)."""
import collections
from pathlib import Path

import pytest

from mikazuki.engines.diffsynth import adapter
from mikazuki.engines.diffsynth.adapter import ensure_cache_space
from mikazuki.engines.diffsynth.inputs import cache_key
from mikazuki.engines.diffsynth.settings import CACHE_DIR_ENV, Runtime, configured_cache_root, remember_cache_dir


@pytest.fixture(autouse=True)
def no_env_override(monkeypatch):
    monkeypatch.delenv(CACHE_DIR_ENV, raising=False)


def test_default_cache_dir_is_project_extension(tmp_path):
    rt = Runtime(tmp_path)
    assert configured_cache_root(rt) == rt.root / "cache"


def test_models_and_encodings_stay_under_selected_root(tmp_path):
    root = configured_cache_root(Runtime(tmp_path), str(tmp_path / "data盘"))
    models = root / "models"
    encodings = models.parent / "encodings"
    assert encodings.parent == models.parent == root


def test_env_override_wins(tmp_path, monkeypatch):
    target = tmp_path / "data盘 cache"
    monkeypatch.setenv(CACHE_DIR_ENV, str(target))
    assert configured_cache_root(Runtime(tmp_path)) == target.resolve()


def _settings_store(monkeypatch, paths):
    class FakeStore:
        def read_settings(self):
            return {"schema_version": 1, "revision": 0, "paths": paths}
    monkeypatch.setattr("mikazuki.user_data.UserDataStore", FakeStore)


def test_settings_absolute_path(tmp_path, monkeypatch):
    target = tmp_path / "shared" / "dscache"
    _settings_store(monkeypatch, {"diffsynth_cache": str(target)})
    assert configured_cache_root(Runtime(tmp_path)) == target.resolve()


def test_settings_relative_path_resolves_against_project_root(tmp_path, monkeypatch):
    _settings_store(monkeypatch, {"diffsynth_cache": "bigdisk/dscache"})
    assert configured_cache_root(Runtime(tmp_path)) == (tmp_path / "bigdisk" / "dscache").resolve()


def test_settings_empty_falls_back_to_default(tmp_path, monkeypatch):
    _settings_store(monkeypatch, {"diffsynth_cache": "  "})
    assert configured_cache_root(Runtime(tmp_path)) == Runtime(tmp_path).root / "cache"


def test_task_config_override_wins_over_env_and_settings(tmp_path, monkeypatch):
    monkeypatch.setenv(CACHE_DIR_ENV, str(tmp_path / "env-cache"))
    _settings_store(monkeypatch, {"diffsynth_cache": str(tmp_path / "settings-cache")})
    target = tmp_path / "task-cache"
    assert configured_cache_root(Runtime(tmp_path), str(target)) == target.resolve()


def test_task_config_relative_override_resolves_against_project_root(tmp_path, monkeypatch):
    assert configured_cache_root(Runtime(tmp_path), "bigdisk/dscache") == (tmp_path / "bigdisk" / "dscache").resolve()


def test_remember_cache_dir_persists_form_value(tmp_path, monkeypatch):
    from mikazuki.user_data import UserDataStore
    monkeypatch.setattr("mikazuki.user_data.UserDataStore", lambda: UserDataStore(root=tmp_path))
    remember_cache_dir(" /data/dscache ")
    stored = UserDataStore(root=tmp_path).read_settings()
    assert stored["paths"]["diffsynth_cache"] == "/data/dscache"


def test_remember_cache_dir_noop_when_empty_or_unchanged(tmp_path, monkeypatch):
    from mikazuki.user_data import UserDataStore
    monkeypatch.setattr("mikazuki.user_data.UserDataStore", lambda: UserDataStore(root=tmp_path))
    remember_cache_dir("")
    assert not (tmp_path / "settings.json").exists()
    remember_cache_dir("/data/dscache")
    revision = UserDataStore(root=tmp_path).read_settings()["revision"]
    remember_cache_dir("/data/dscache")
    assert UserDataStore(root=tmp_path).read_settings()["revision"] == revision


def _models(tmp_path, conversions):
    models = []
    for component, plan in conversions.items():
        source = tmp_path / f"{component}.safetensors"
        source.write_bytes(b"\0" * 1024)
        models.append({"component": component, "files": [str(source)], "conversion": plan})
    return models


def test_identity_conversion_needs_no_space(tmp_path):
    models = _models(tmp_path, {"dit_path": {"a": ("a", "identity")}})
    ensure_cache_space(models, tmp_path / "missing-cache")


def test_cached_manifest_skips_space_check(tmp_path, monkeypatch):
    models = _models(tmp_path, {"dit_path": {"a": ("b", "first_half")}})
    cache_dir = tmp_path / "cache"
    directory = cache_dir / f"v1-dit_path-{cache_key(models[0]['files'])}"
    directory.mkdir(parents=True)
    (directory / "files.json").write_text("[]")
    monkeypatch.setattr(adapter.shutil, "disk_usage", lambda p: collections.namedtuple("usage", "total used free")(0, 0, 1))
    ensure_cache_space(models, cache_dir)


def test_insufficient_space_fails_with_readable_message(tmp_path, monkeypatch):
    models = _models(tmp_path, {"dit_path": {"a": ("b", "first_half")}})
    monkeypatch.setattr(adapter.shutil, "disk_usage", lambda p: collections.namedtuple("usage", "total used free")(0, 0, 1))
    with pytest.raises(ValueError, match="空间不足"):
        ensure_cache_space(models, tmp_path / "cache")


def test_sufficient_space_passes(tmp_path):
    models = _models(tmp_path, {"dit_path": {"a": ("b", "first_half")}})
    ensure_cache_space(models, tmp_path / "cache")

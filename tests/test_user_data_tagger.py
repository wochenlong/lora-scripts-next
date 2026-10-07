from types import SimpleNamespace

from mikazuki.tagger import local_models
from mikazuki.user_data import UserDataStore


def test_tagger_uses_user_model_directory(tmp_path, monkeypatch):
    monkeypatch.delenv(local_models.TAGGER_MODELS_DIR_ENV, raising=False)
    store = UserDataStore(tmp_path / "project" / "user_data")
    store.patch_settings({"paths": {"tagger_models": {"wd-test": "./weights/wd"}}}, 0)
    monkeypatch.setattr(local_models, "UserDataStore", lambda: store)
    target = tmp_path / "project" / "weights" / "wd"
    assert local_models.local_model_dir("wd-test") == target
    target.mkdir(parents=True)
    (target / "model.onnx").write_bytes(b"model")
    (target / "tags.csv").write_text("tags")
    model = SimpleNamespace(model_path="model.onnx", tags_path="tags.csv")
    assert local_models.local_model_asset_paths("wd-test", model) == (target / "model.onnx", target / "tags.csv")


def test_explicit_tagger_root_env_wins(tmp_path, monkeypatch):
    store = UserDataStore(tmp_path / "user_data")
    store.patch_settings({"paths": {"tagger_models": {"wd-test": "./default"}}}, 0)
    monkeypatch.setattr(local_models, "UserDataStore", lambda: store)
    monkeypatch.setenv(local_models.TAGGER_MODELS_DIR_ENV, str(tmp_path / "explicit"))
    assert local_models.local_model_dir("wd-test") == tmp_path / "explicit" / "wd14" / "wd-test"

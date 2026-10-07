import pytest

from mikazuki.llm.contracts import LLMContractError
from mikazuki.tagger.catalog import TAG_MODEL_IDS, model_catalog, validate_model_selection


def _profile(identifier, source="remote", vision=True):
    return {"id": identifier, "name": identifier, "model": "Qwen/Qwen3-VL", "source": source,
            "capabilities": ["text", "vision"] if vision else ["text"], "languages": ["zh-CN"],
            "ready": True, "enabled": True, "api_key": "private-value", "endpoint": "https://example.test"}


def test_model_catalog_preserves_tag_ids_and_excludes_text_profiles(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_TAGGER_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr("huggingface_hub.try_to_load_from_cache", lambda *args, **kwargs: None)
    config = {"profiles": [_profile("text", vision=False), _profile("remote"), _profile("local", "local-endpoint")]}
    models = model_catalog(config, {"installed": False})
    assert [item["id"] for item in models if item["output"] == "tag"] == list(TAG_MODEL_IDS)
    assert not any(item["id"] == "llm:text" for item in models)
    assert next(item for item in models if item["id"] == "llm:remote")["runtime"] == "api"
    assert next(item for item in models if item["id"] == "llm:local")["runtime"] == "local"
    assert next(item for item in models if item["id"] == "llm:qwen3-vl-2b-local")["ready"] is False
    assert "private-value" not in str(models)
    assert "https://example.test" not in str(models)


def test_catalog_reports_complete_local_tag_assets_without_download(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKAZUKI_TAGGER_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr("huggingface_hub.try_to_load_from_cache", lambda *args, **kwargs: None)
    directory = tmp_path / "wd14" / "wd14-convnextv2-v2"
    directory.mkdir(parents=True)
    (directory / "model.onnx").write_bytes(b"fixture")
    (directory / "selected_tags.csv").write_bytes(b"fixture")
    models = model_catalog({}, {})
    assert models[0]["downloaded"] is True
    assert models[1]["downloaded"] is False


@pytest.mark.parametrize("runtime,profile_id,model_id", [
    ("local", "remote", "llm:remote"), ("api", "local", "llm:remote"), ("api", "remote", "llm:text"),
])
def test_model_selection_cannot_forge_runtime_or_capabilities(runtime, profile_id, model_id):
    config = {"profiles": [_profile("remote"), _profile("text", vision=False)]}
    with pytest.raises(LLMContractError):
        validate_model_selection({"mode": "natural", "runtime": runtime, "profile_id": profile_id, "model_id": model_id}, config)


def test_model_selection_accepts_valid_tag_and_caption():
    validate_model_selection({"mode": "tag", "runtime": "local", "model_id": TAG_MODEL_IDS[0], "interrogator_model": TAG_MODEL_IDS[0]}, {})
    validate_model_selection({"mode": "natural", "runtime": "api", "model_id": "llm:remote", "profile_id": "remote"}, {"profiles": [_profile("remote")]})


@pytest.mark.parametrize("fields", [{"prompt": "caption prompt"}, {"temperature": 0.5}, {"profile_id": "remote"}])
def test_legacy_tag_contract_rejects_caption_only_parameters(fields):
    from pydantic import ValidationError
    from mikazuki.app.models import TaggerInterrogateRequest
    with pytest.raises(ValidationError):
        TaggerInterrogateRequest(path="images", **fields)

"""Tagger progress API smoke tests (no ONNX / no real images)."""

from fastapi.testclient import TestClient

from mikazuki.app.application import app
from mikazuki.tagger import model_fetch as model_fetch_module
from mikazuki.tagger.model_fetch import (
    describe_interrogator_asset_status,
    format_tagger_download_error,
    use_download_endpoint,
)
from mikazuki.tagger.interrogator import available_interrogators
from mikazuki.tagger.interrogators import wd14 as wd14_module
from mikazuki.tagger.progress import tagger_progress
from mikazuki.tagger.interrogators.wd14 import WaifuDiffusionInterrogator
from mikazuki.tagger.local_models import (
    local_model_asset_paths,
    local_model_dir,
)


def test_tagger_status_idle():
    tagger_progress.reset_idle("test")
    client = TestClient(app)
    r = client.get("/api/tagger/status")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert data["data"]["phase"] == "idle"


def test_tagger_busy_guard():
    tagger_progress.reset_idle("test")
    assert tagger_progress.try_begin("downloading", "wd14-convnextv2-v2", "busy test")
    client = TestClient(app)
    r = client.post("/api/tagger/prefetch", json={"interrogator_model": "wd14-convnextv2-v2"})
    assert r.json()["status"] == "fail"
    tagger_progress.release()
    tagger_progress.reset_idle("test")


def test_tagger_html_serves_progress_script():
    # /tagger.html now serves the Vue SPA shell; the progress UI lives in the
    # Vue tagger page (TaggerPage.vue), not a standalone tagger-progress.js.
    client = TestClient(app)
    r = client.get("/tagger.html")
    assert r.status_code == 200
    assert 'id="app"' in r.text


def test_tagger_default_download_endpoint_preserves_existing_hf_endpoint(monkeypatch):
    monkeypatch.setenv("HF_ENDPOINT", "https://hf-mirror.com")

    with use_download_endpoint(""):
        import os

        assert os.environ["HF_ENDPOINT"] == "https://hf-mirror.com"

    assert os.environ["HF_ENDPOINT"] == "https://hf-mirror.com"


def test_tagger_local_model_directory_resolves_by_model_key(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKAZUKI_TAGGER_MODELS_DIR", str(tmp_path / "tagger-models"))

    expected = tmp_path / "tagger-models" / "wd14" / "wd14-convnextv2-v2"

    assert local_model_dir("wd14-convnextv2-v2") == expected


def test_tagger_assets_ready_when_files_exist_in_wd14_local_model_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKAZUKI_TAGGER_MODELS_DIR", str(tmp_path / "tagger-models"))
    model_dir = tmp_path / "tagger-models" / "wd14" / "wd14-convnextv2-v2"
    model_dir.mkdir(parents=True)
    (model_dir / "model.onnx").write_bytes(b"fake onnx")
    (model_dir / "selected_tags.csv").write_text("name,category\n", encoding="utf-8")

    interrogator = WaifuDiffusionInterrogator(
        "wd14-convnextv2-v2",
        repo_id="SmilingWolf/wd-v1-4-convnextv2-tagger-v2",
        revision="v2.0",
    )

    assert local_model_asset_paths("wd14-convnextv2-v2", interrogator) == (
        model_dir / "model.onnx",
        model_dir / "selected_tags.csv",
    )
    assert interrogator.download() == (
        model_dir / "model.onnx",
        model_dir / "selected_tags.csv",
    )


def test_wd_vit_v3_download_uses_the_same_local_directory_as_asset_precheck(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MIKAZUKI_TAGGER_MODELS_DIR", str(tmp_path / "tagger-models"))
    model_dir = tmp_path / "tagger-models" / "wd14" / "wd-vit-v3"
    model_dir.mkdir(parents=True)
    (model_dir / "model.onnx").write_bytes(b"fake onnx")
    (model_dir / "selected_tags.csv").write_text("name,category\n", encoding="utf-8")

    def fail_if_huggingface_is_called(**_kwargs):
        raise AssertionError("local wd-vit-v3 assets must not contact Hugging Face")

    monkeypatch.setattr(wd14_module, "hf_hub_download", fail_if_huggingface_is_called)
    interrogator = available_interrogators["wd-vit-v3"]

    assert local_model_asset_paths("wd-vit-v3", interrogator) == (
        model_dir / "model.onnx",
        model_dir / "selected_tags.csv",
    )
    assert interrogator.download() == (
        model_dir / "model.onnx",
        model_dir / "selected_tags.csv",
    )


def test_wd14_moat_v2_download_uses_the_same_local_directory_as_asset_precheck(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MIKAZUKI_TAGGER_MODELS_DIR", str(tmp_path / "tagger-models"))
    model_dir = tmp_path / "tagger-models" / "wd14" / "wd14-moat-v2"
    model_dir.mkdir(parents=True)
    (model_dir / "model.onnx").write_bytes(b"fake onnx")
    (model_dir / "selected_tags.csv").write_text("name,category\n", encoding="utf-8")

    def fail_if_huggingface_is_called(**_kwargs):
        raise AssertionError("local wd14-moat-v2 assets must not contact Hugging Face")

    monkeypatch.setattr(wd14_module, "hf_hub_download", fail_if_huggingface_is_called)
    interrogator = available_interrogators["wd14-moat-v2"]

    assert local_model_asset_paths("wd14-moat-v2", interrogator) == (
        model_dir / "model.onnx",
        model_dir / "selected_tags.csv",
    )
    assert interrogator.download() == (
        model_dir / "model.onnx",
        model_dir / "selected_tags.csv",
    )


def test_renamed_wd_models_keep_their_previous_local_directory_compatible(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MIKAZUKI_TAGGER_MODELS_DIR", str(tmp_path / "tagger-models"))

    def fail_if_huggingface_is_called(**_kwargs):
        raise AssertionError("legacy local model directories must remain offline")

    monkeypatch.setattr(wd14_module, "hf_hub_download", fail_if_huggingface_is_called)

    for model_key, previous_name in (
        ("wd-vit-v3", "wd14-vit-v3"),
        ("wd14-moat-v2", "wd-v1-4-moat-tagger-v2"),
    ):
        model_dir = tmp_path / "tagger-models" / "wd14" / previous_name
        model_dir.mkdir(parents=True)
        (model_dir / "model.onnx").write_bytes(b"fake onnx")
        (model_dir / "selected_tags.csv").write_text(
            "name,category\n", encoding="utf-8"
        )

        assert available_interrogators[model_key].download() == (
            model_dir / "model.onnx",
            model_dir / "selected_tags.csv",
        )


def test_wd14_download_uses_complete_huggingface_cache_without_network(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MIKAZUKI_TAGGER_MODELS_DIR", str(tmp_path / "tagger-models"))
    cached_model = tmp_path / "huggingface-cache" / "model.onnx"
    cached_tags = tmp_path / "huggingface-cache" / "selected_tags.csv"
    cached_model.parent.mkdir(parents=True)
    cached_model.write_bytes(b"fake onnx")
    cached_tags.write_text("name,category\n", encoding="utf-8")
    calls = []

    def cached_hf_download(**kwargs):
        calls.append(kwargs)
        assert kwargs.get("local_files_only") is True
        return cached_model if kwargs["filename"] == "model.onnx" else cached_tags

    monkeypatch.setattr(wd14_module, "hf_hub_download", cached_hf_download)
    interrogator = WaifuDiffusionInterrogator(
        "wd-vit-v3",
        repo_id="SmilingWolf/wd-vit-tagger-v3",
    )

    assert interrogator.download() == (cached_model, cached_tags)
    assert [call["filename"] for call in calls] == [
        "model.onnx",
        "selected_tags.csv",
    ]


def test_describe_interrogator_asset_status_reports_complete_hf_cache(monkeypatch):
    monkeypatch.setattr(
        model_fetch_module,
        "_file_cached",
        lambda _kwargs, _filename: True,
    )
    interrogator = WaifuDiffusionInterrogator(
        "wd-vit-v3",
        repo_id="SmilingWolf/wd-vit-tagger-v3",
    )

    ready, message = describe_interrogator_asset_status("wd-vit-v3", interrogator)

    assert ready is True
    assert "Hugging Face 本地缓存" in message
    assert "未在本地" not in message


def test_tagger_assets_keep_legacy_flat_local_model_dir_compatible(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKAZUKI_TAGGER_MODELS_DIR", str(tmp_path / "tagger-models"))
    model_dir = tmp_path / "tagger-models" / "wd14-convnextv2-v2"
    model_dir.mkdir(parents=True)
    (model_dir / "model.onnx").write_bytes(b"fake onnx")
    (model_dir / "selected_tags.csv").write_text("name,category\n", encoding="utf-8")

    interrogator = WaifuDiffusionInterrogator(
        "wd14-convnextv2-v2",
        repo_id="SmilingWolf/wd-v1-4-convnextv2-tagger-v2",
        revision="v2.0",
    )

    assert local_model_asset_paths("wd14-convnextv2-v2", interrogator) == (
        model_dir / "model.onnx",
        model_dir / "selected_tags.csv",
    )


def test_describe_interrogator_asset_status_reports_local_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKAZUKI_TAGGER_MODELS_DIR", str(tmp_path / "tagger-models"))
    monkeypatch.setattr(
        model_fetch_module,
        "_file_cached",
        lambda _kwargs, _filename: False,
    )
    interrogator = WaifuDiffusionInterrogator(
        "wd-vit-large-tagger-v3",
        repo_id="SmilingWolf/wd-vit-large-tagger-v3",
    )
    ready, msg = describe_interrogator_asset_status("wd-vit-large-tagger-v3", interrogator)
    assert ready is False
    assert "未在本地" in msg
    assert "tagger-models" in msg
    assert "SmilingWolf/wd-vit-large-tagger-v3" in msg


def test_format_tagger_download_error_network_hint():
    from huggingface_hub.errors import LocalEntryNotFoundError

    hint = format_tagger_download_error(
        "wd-vit-large-tagger-v3",
        LocalEntryNotFoundError("Cannot find file"),
    )
    assert "huggingface.co" in hint
    assert "未在本地" in hint


def test_format_tagger_download_error_modelscope_404():
    hint = format_tagger_download_error(
        "wd-vit-large-tagger-v3",
        Exception("Repo SmilingWolf/wd-vit-large-tagger-v3 not exists on modelscope.cn"),
    )
    assert "魔搭" in hint
    assert "SmilingWolf" in hint

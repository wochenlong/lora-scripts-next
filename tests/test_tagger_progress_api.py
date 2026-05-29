"""Tagger progress API smoke tests (no ONNX / no real images)."""

from fastapi.testclient import TestClient

from mikazuki.app.application import app
from mikazuki.tagger.model_fetch import use_download_endpoint
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
    client = TestClient(app)
    r = client.get("/tagger.html")
    assert r.status_code == 200
    assert "tagger-progress.js" in r.text


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

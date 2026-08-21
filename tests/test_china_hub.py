import importlib.util
import os

import pytest

from mikazuki.china_hub import (
    HF_TO_MODELSCOPE_REPOS,
    enable_china_hub,
    hub_backend,
    is_hf_only_repo,
    remap_hf_repo_id,
)


def test_remap_hf_repo_id():
    assert remap_hf_repo_id("openai/clip-vit-large-patch14") == "AI-ModelScope/clip-vit-large-patch14"
    assert remap_hf_repo_id("google/t5-v1_1-xxl") == "google/t5-v1_1-xxl"
    assert remap_hf_repo_id("laion/CLIP-ViT-bigG-14-laion2B-39B-b160k") == (
        "laion/CLIP-ViT-bigG-14-laion2B-39B-b160k"
    )


def test_hub_backend_respects_explicit_modelscope(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MIKAZUKI_HUB_BACKEND", "modelscope")
    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    assert hub_backend() == "modelscope"


def test_hub_backend_hf_mirror_endpoint(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MIKAZUKI_HUB_BACKEND", "auto")
    monkeypatch.setenv("HF_ENDPOINT", "https://hf-mirror.com")
    assert hub_backend() == "modelscope"


def test_smilingwolf_tagger_repos_are_hf_only():
    assert is_hf_only_repo("SmilingWolf/wd-vit-large-tagger-v3")
    assert is_hf_only_repo("cella110n/cl_tagger")
    assert not is_hf_only_repo("openai/clip-vit-large-patch14")


@pytest.mark.skipif(
    importlib.util.find_spec("modelscope") is None,
    reason="modelscope not installed",
)
def test_smilingwolf_download_bypasses_modelscope_patch(monkeypatch: pytest.MonkeyPatch):
    import mikazuki.china_hub as china_hub
    import huggingface_hub

    china_hub._PATCHED = False
    china_hub._ORIGINAL_HF_HUB_DOWNLOAD = None
    calls: list[tuple[tuple, dict]] = []

    def fake_original(*args, **kwargs):
        calls.append((args, kwargs))
        return "/tmp/model.onnx"

    monkeypatch.setenv("MIKAZUKI_HUB_BACKEND", "modelscope")
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_original)
    import transformers  # noqa: F401 — patch_hub expects HF libs importable

    try:
        enabled = enable_china_hub(force=True)
    except ImportError as exc:
        pytest.skip(f"modelscope patch_hub unavailable in this env: {exc}")
    if not enabled:
        pytest.skip("modelscope not installed")

    path = huggingface_hub.hf_hub_download(
        repo_id="SmilingWolf/wd-vit-large-tagger-v3",
        filename="model.onnx",
    )
    assert path == "/tmp/model.onnx"
    assert len(calls) == 1
    assert calls[0][1]["repo_id"] == "SmilingWolf/wd-vit-large-tagger-v3"
    assert "HF_ENDPOINT" not in os.environ or os.environ.get("HF_ENDPOINT") != "https://hf-mirror.com"


def test_enable_china_hub_requires_modelscope(monkeypatch: pytest.MonkeyPatch):
    import mikazuki.china_hub as china_hub

    monkeypatch.setattr(china_hub, "_PATCHED", False)
    monkeypatch.setenv("MIKAZUKI_HUB_BACKEND", "huggingface")
    assert enable_china_hub() is False


@pytest.mark.skipif(
    importlib.util.find_spec("modelscope") is None,
    reason="modelscope not installed",
)
def test_enable_china_hub_patches_transformers_download(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import mikazuki.china_hub as china_hub

    china_hub._PATCHED = False
    monkeypatch.setenv("MIKAZUKI_HUB_BACKEND", "modelscope")
    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    import transformers  # noqa: F401 — patch_hub expects HF libs importable

    try:
        enabled = enable_china_hub(force=True)
    except ImportError as exc:
        pytest.skip(f"modelscope patch_hub unavailable in this env: {exc}")
    if not enabled:
        pytest.skip("modelscope not installed")

    cache = tmp_path / "hf-cache"
    from transformers import CLIPTokenizer

    tok = CLIPTokenizer.from_pretrained(
        "openai/clip-vit-large-patch14",
        cache_dir=str(cache),
        force_download=True,
    )
    assert tok.vocab_size == 49408
    assert any(cache.rglob("vocab.json"))

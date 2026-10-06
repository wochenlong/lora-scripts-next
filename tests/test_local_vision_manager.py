import asyncio
import hashlib

import pytest

from mikazuki.llm import local_vision
from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.tag_translation.local_model_service import LocalModelService
from mikazuki.tag_translation.translation_config import OnlineServiceConfig
from tests.test_tag_translation_local_model import FakeSessionFactory


def make_manager(tmp_path):
    path = tmp_path / "translation.json"
    return local_vision.LocalVisionService(tmp_path, OnlineServiceConfig(path), UnifiedConfigStore(path))


def test_vision_and_translation_share_runtime_directory(tmp_path):
    vision = make_manager(tmp_path)
    translation = LocalModelService(tmp_path / "models", OnlineServiceConfig(tmp_path / "translation.json"))
    assert vision.runtime_root == translation.runtime_root
    assert vision.runtime_executable == translation.runtime_executable
    assert not vision.status()["installed"]
    assert "--mmproj" in vision._runtime_extra_arguments()


def test_model_and_mmproj_both_need_their_pinned_hash(tmp_path, monkeypatch):
    payload = b"GGUF" + b"a" * 12
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(local_vision, "FILES", (("model.gguf", len(payload), digest), ("mmproj.gguf", len(payload), digest)))
    service = make_manager(tmp_path)
    service.session_factory = FakeSessionFactory(payload)
    asyncio.run(service._download())
    assert service.status()["installed"]
    service._validate_model_install()
    (service.root / "mmproj.gguf").write_bytes(b"x" * len(payload))
    with pytest.raises(RuntimeError, match="integrity"):
        service._validate_model_install()


def test_corrupt_download_is_not_promoted_to_valid_asset(tmp_path, monkeypatch):
    monkeypatch.setattr(local_vision, "FILES", (("model.gguf", 16, "0" * 64), ("mmproj.gguf", 16, "0" * 64)))
    service = make_manager(tmp_path)
    service.session_factory = FakeSessionFactory(b"GGUF" + b"x" * 12)
    asyncio.run(service._download())
    assert service.status()["state"] == "error"
    assert not (service.root / "model.gguf").exists()
    assert not list(service.root.glob("*.download"))


def test_existing_configured_runtime_is_reused_after_restart(tmp_path):
    runtime = tmp_path / "models" / "llama-runtime" / "nested" / "llama-server.exe"
    runtime.parent.mkdir(parents=True)
    runtime.write_bytes(b"x" * 2048)
    path = tmp_path / "translation.json"
    OnlineServiceConfig(path).save({"local": {"runtime_path": str(runtime)}})
    manager = make_manager(tmp_path)
    assert manager.runtime_executable == runtime
    assert manager.status()["runtime_installed"] is True

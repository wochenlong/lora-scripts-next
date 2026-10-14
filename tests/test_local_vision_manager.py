import asyncio
import hashlib
import json

import pytest

from mikazuki.llm import local_vision
from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.tag_translation.translation_config import OnlineServiceConfig
from tests.test_tag_translation_local_model import FakeSessionFactory


def make_manager(tmp_path):
    path = tmp_path / "translation.json"
    return local_vision.LocalVisionService(tmp_path, OnlineServiceConfig(path), UnifiedConfigStore(path))


def test_shared_managers_resolve_same_pinned_runtime_directory(tmp_path):
    vision = make_manager(tmp_path)
    # A reconstructed manager must resolve the same pinned, versioned runtime
    # location instead of the legacy unversioned directory. The text alias
    # singleton delegation has its own isolated regression test.
    second = make_manager(tmp_path)
    assert vision.runtime_root == second.runtime_root
    assert vision.runtime_executable == second.runtime_executable
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


def test_legacy_configured_runtime_is_not_reused_after_restart(tmp_path):
    runtime = tmp_path / "models" / "llama-runtime" / "nested" / "llama-server.exe"
    runtime.parent.mkdir(parents=True)
    runtime.write_bytes(b"x" * 2048)
    path = tmp_path / "translation.json"
    # The migrated save adapter intentionally does not write this obsolete
    # runtime field; persist a real legacy fixture to prove it is ignored.
    path.write_text(json.dumps({"local": {"runtime_path": str(runtime)}}), encoding="utf-8")
    before = path.read_bytes()
    assert OnlineServiceConfig(path).load()["local"]["runtime_path"] == str(runtime)
    manager = make_manager(tmp_path)
    assert manager.runtime_executable != runtime
    assert manager.runtime_executable.parts[-3:] == ("b11327", manager.runtime_root.name, "llama-server.exe")
    assert manager.status()["runtime_installed"] is False
    assert manager.runtime_root.parent.parent == tmp_path / "models" / "llama-runtime"
    assert path.read_bytes() == before
    assert runtime.read_bytes() == b"x" * 2048

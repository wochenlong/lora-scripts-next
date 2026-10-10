import asyncio
import hashlib
import zipfile

import pytest

from mikazuki.llm import model_manifest
from mikazuki.llm.managed_model import ManagedModelService
from mikazuki.llm.scheduler import LocalRequestScheduler


class Store:
    def __init__(self, path):
        self.path = path

    def load(self):
        return {"version": 5, "profiles": [], "routes": {}, "prompt_presets": [], "cache": {"caption": False, "translation": False}}


def test_qwen35_manifest_locks_shared_vision_text_assets():
    value = model_manifest.manifest()
    assert value["id"] == "qwen3.5-2b-local"
    assert value["revision"] == "f6d5376be1edb4d416d56da11e5397a961aca8ae"
    assert value["capabilities"] == ["text", "vision"]
    assert value["languages"] == ["en", "zh-CN"]
    assert value["files"][1]["sha256"] == "7035e9cb8d7c6a9681d07eef9a364783e86ea4cd73faab2eabb4f43a101830c7"
    assert value["runtime_package"]["filename"] == "llama-b11327-bin-win-cpu-x64.zip"


def test_scheduler_has_one_active_and_two_waiting_slots():
    async def run():
        scheduler = LocalRequestScheduler(max_waiting=2)
        active = await scheduler.acquire()
        pending = [asyncio.create_task(scheduler.acquire()) for _ in range(2)]
        await asyncio.sleep(0)
        assert scheduler.snapshot()["active"] == 1
        assert scheduler.snapshot()["waiting"] == 2
        with pytest.raises(Exception) as error:
            await scheduler.acquire()
        assert error.value.code == "llm_local_queue_full"
        pending[0].cancel()
        await asyncio.gather(pending[0], return_exceptions=True)
        assert scheduler.snapshot()["waiting"] == 1
        scheduler._release(active)
        next_ticket = await pending[1]
        scheduler._release(next_ticket)
        assert scheduler.snapshot()["active"] == 0
        assert scheduler.snapshot()["waiting"] == 0

    asyncio.run(run())


def test_model_install_requires_both_exact_files(tmp_path, monkeypatch):
    payload = b"model-payload"
    digest = hashlib.sha256(payload).hexdigest()
    files = (("model.gguf", len(payload), digest), ("mmproj.gguf", len(payload), digest))
    service = ManagedModelService(tmp_path, Store(tmp_path / "config.json"), files=files)
    for name, _, _ in files:
        (service.root / name).write_bytes(payload)
    service._validate_model_install()
    assert service.status()["installed"] is True
    (service.root / "mmproj.gguf").write_bytes(b"wrong")
    with pytest.raises(RuntimeError, match="integrity"):
        service._validate_model_install()
    assert service.status()["installed"] is False


def test_runtime_archive_rejects_wrong_executable_hash(tmp_path, monkeypatch):
    payload = b"model-payload"
    digest = hashlib.sha256(payload).hexdigest()
    files = (("model.gguf", len(payload), digest), ("mmproj.gguf", len(payload), digest))
    service = ManagedModelService(tmp_path, Store(tmp_path / "config.json"), files=files)
    archive_path = service.archive_path
    archive_path.parent.mkdir(parents=True)
    executable = b"server" * 100
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("bin/llama-server.exe", executable)
        archive.writestr("bin/llama.dll", b"dll")
    monkeypatch.setattr(model_manifest, "RUNTIME_SIZE", archive_path.stat().st_size)
    monkeypatch.setattr(model_manifest, "RUNTIME_SHA256", hashlib.sha256(archive_path.read_bytes()).hexdigest())
    with pytest.raises(RuntimeError, match="executable"):
        service._archive_inventory()

import asyncio
import io
import zipfile

import pytest

from mikazuki.tag_translation.local_model_service import (
    MODEL_MIRROR_URL,
    RUNTIME_ASSET_NAME,
    RUNTIME_RELEASE_TAG,
    LocalModelService,
)


class Config:
    def load(self):
        return {
            "local": {
                "enabled": False,
                "endpoint": "http://127.0.0.1:8081/v1/chat/completions",
                "runtime_path": "",
                "port": 8081,
                "context_length": 2048,
            }
        }

    def save(self, _payload):
        return None


class FakeResponse:
    def __init__(self, payload, content_type="application/octet-stream"):
        self.status = 200
        self.headers = {"Content-Length": str(len(payload))}
        self.content = self
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def __aiter__(self):
        return self

    async def iter_chunked(self, _size):
        yield self._payload
        self._payload = b""

    async def __anext__(self):
        if not self._payload:
            raise StopAsyncIteration
        payload, self._payload = self._payload, b""
        return payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def get(self, *_args, **_kwargs):
        return FakeResponse(self.payload)


class FakeSessionFactory:
    def __init__(self, payload):
        self.payload = payload

    def __call__(self, **_kwargs):
        return FakeSession(self.payload)


def test_local_model_status_is_safe_before_install(tmp_path):
    status = LocalModelService(tmp_path, Config()).status()
    assert status["state"] == "missing"
    assert status["installed"] is False
    assert status["model_id"] == "qwen3.5-0.8b-q4_0"
    assert status["port"] == 0


def test_runtime_port_is_allocated_by_the_os():
    first = LocalModelService._allocate_loopback_port()
    second = LocalModelService._allocate_loopback_port()
    assert first > 0
    assert second > 0


def test_managed_assets_have_reachable_mirror_and_windows_cpu_runtime():
    assert "hf-mirror.com" in MODEL_MIRROR_URL
    assert RUNTIME_RELEASE_TAG == "b11327"
    assert RUNTIME_ASSET_NAME.endswith("win-cpu-x64.zip")


def test_local_runtime_requires_explicit_executable(tmp_path):
    service = LocalModelService(tmp_path, Config())
    with pytest.raises(RuntimeError, match="Qwen GGUF"):
        asyncio.run(service.start_runtime())


def test_model_download_accepts_a_valid_gguf_payload(tmp_path):
    service = LocalModelService(tmp_path, Config())
    service.session_factory = FakeSessionFactory(b"GGUF" + b"x" * 32)
    asyncio.run(service._download())
    assert service.model_path.read_bytes().startswith(b"GGUF")
    assert service.status()["state"] == "ready"


def test_runtime_download_extracts_llama_server_from_windows_zip(tmp_path):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("llama-b11327/bin/llama-server.exe", b"x" * 2048)
    service = LocalModelService(tmp_path, Config())
    service.session_factory = FakeSessionFactory(archive.getvalue())
    asyncio.run(service._download_runtime())
    assert service.runtime_executable.exists()
    assert service.status()["runtime_state"] == "ready"


def test_setup_reconciles_existing_runtime_after_process_restart(tmp_path):
    service = LocalModelService(tmp_path, Config())
    service.model_path.write_bytes(b"GGUF" + b"x" * 32)
    service.runtime_root.mkdir(parents=True)
    service.runtime_executable.write_bytes(b"x" * 2048)
    started = False

    async def fake_start_runtime():
        nonlocal started
        started = True
        return service.status()

    service.start_runtime = fake_start_runtime
    service._runtime_install.update(state="installing")
    asyncio.run(service._setup())

    assert service.status()["runtime_state"] == "ready"
    assert started is True


def test_setup_surfaces_runtime_start_failure(tmp_path):
    service = LocalModelService(tmp_path, Config())
    service.model_path.write_bytes(b"GGUF" + b"x" * 32)
    service.runtime_root.mkdir(parents=True)
    service.runtime_executable.write_bytes(b"x" * 2048)

    async def failed_start_runtime():
        raise RuntimeError("llama-server did not become healthy")

    service.start_runtime = failed_start_runtime
    asyncio.run(service._setup())

    status = service.status()
    assert status["state"] == "error"
    assert "did not become healthy" in (status["error"] or "")

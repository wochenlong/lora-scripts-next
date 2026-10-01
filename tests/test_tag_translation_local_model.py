import asyncio

import pytest

from mikazuki.tag_translation.local_model_service import LocalModelService


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


def test_local_model_status_is_safe_before_install(tmp_path):
    status = LocalModelService(tmp_path, Config()).status()
    assert status["state"] == "missing"
    assert status["installed"] is False
    assert status["model_id"] == "qwen3.5-0.8b-q4_0"


def test_local_runtime_requires_explicit_executable(tmp_path):
    service = LocalModelService(tmp_path, Config())
    with pytest.raises(RuntimeError, match="Qwen GGUF"):
        asyncio.run(service.start_runtime())

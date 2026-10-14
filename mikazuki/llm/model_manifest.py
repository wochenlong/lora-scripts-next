"""共享本地模型唯一锁：官方 Qwen 原模型、Unsloth 社区量化。"""
from __future__ import annotations

import hashlib
import json
import platform

ASSET_ID = "qwen3.5-2b-local"
REVISION = "f6d5376be1edb4d416d56da11e5397a961aca8ae"
REPOSITORY = "unsloth/Qwen3.5-2B-GGUF"
FILES = (
    ("Qwen3.5-2B-Q4_K_M.gguf", 1280835840, "aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223"),
    ("mmproj-F16.gguf", 668227264, "7035e9cb8d7c6a9681d07eef9a364783e86ea4cd73faab2eabb4f43a101830c7"),
)
RUNTIME_VERSION = "b11327"
RUNTIME_FILENAME = "llama-b11327-bin-win-cpu-x64.zip"
RUNTIME_SIZE = 19275534
RUNTIME_SHA256 = "4ac11772e7f9a313346ff2f4212b0608dd181130df81b9070cef377102faba8f"
EXECUTABLE_SHA256 = "32d43779061d318ab36d0cf8156f314f81ac7e5b805298b7fe9facf3cf0cc82d"
RUNTIME_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{RUNTIME_VERSION}/{RUNTIME_FILENAME}"
CAPABILITIES = ("text", "vision")
LANGUAGES = ("en", "zh-CN")


def platform_supported():
    return platform.system() == "Windows" and platform.machine().lower() in {"amd64", "x86_64"}


def manifest():
    return {
        "id": ASSET_ID, "model": FILES[0][0], "mmproj": FILES[1][0], "source": REPOSITORY,
        "revision": REVISION, "license": "Apache-2.0", "quantization_publisher": "Unsloth (community)",
        "files": [{"name": name, "size_bytes": size, "sha256": sha,
                   "url": f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}"} for name, size, sha in FILES],
        "capabilities": list(CAPABILITIES), "languages": list(LANGUAGES),
        "estimated_download_bytes": sum(size for _, size, _ in FILES) + RUNTIME_SIZE,
        "estimated_peak_rss_bytes": None,
        "runtime": f"llama.cpp {RUNTIME_VERSION}",
        "runtime_package": {"filename": RUNTIME_FILENAME, "size_bytes": RUNTIME_SIZE, "sha256": RUNTIME_SHA256,
                            "executable_sha256": EXECUTABLE_SHA256, "url": RUNTIME_URL, "platform": "windows-x64-cpu"},
        "supported": platform_supported(),
        "notes": "远程优先；本地显式兜底。安装后真实文本和视觉诊断都通过才可用；当前一键安装支持 Windows x64 CPU。",
    }


def model_fingerprint():
    payload = {"asset_id": ASSET_ID, "revision": REVISION, "files": FILES,
               "runtime": RUNTIME_VERSION, "runtime_sha256": RUNTIME_SHA256}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

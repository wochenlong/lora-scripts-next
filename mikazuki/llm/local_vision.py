"""Qwen visual assets using the existing shared llama.cpp lifecycle."""
from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path

import aiohttp

from mikazuki.tag_translation.local_model_service import LocalModelService, utc_now


ASSET_ID = "qwen3-vl-2b-local"
REVISION = "52d6c8ffea26cc873ac5ad116f8631268d7eb503"
REPOSITORY = "Qwen/Qwen3-VL-2B-Instruct-GGUF"
FILES = (
    ("Qwen3VL-2B-Instruct-Q4_K_M.gguf", 1107409952, "089d75c52f4b7ffc56ba998ffc50aae89fcafc755f9e7208aacca281dca6c2ae"),
    ("mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf", 445053216, "f9a68fabba69c3b81e153367b2c7521030b0fa8bb0de400c9599c8e6725f9c82"),
)


def asset_digest(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LocalVisionService(LocalModelService):
    def __init__(self, translation_root, legacy_config_store, unified_config_store):
        translation_root = Path(translation_root)
        super().__init__(
            translation_root / "models" / ASSET_ID / REVISION,
            legacy_config_store,
            runtime_root=translation_root / "models" / "llama-runtime",
        )
        self.model_path = self.root / FILES[0][0]
        self.mmproj_path = self.root / FILES[1][0]
        self.unified_config_store = unified_config_store
        configured = legacy_config_store.load().get("local", {}).get("runtime_path")
        if configured and Path(configured).is_file():
            self.runtime_executable = Path(configured)
            self._runtime_install.update(state="ready")

    def _complete(self):
        return all((self.root / name).is_file() and (self.root / name).stat().st_size == size for name, size, _sha in FILES)

    def status(self):
        data = super().status()
        data.update({
            "model_id": ASSET_ID,
            "model_filename": FILES[0][0],
            "model_url": f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{FILES[0][0]}",
            "installed": self._complete(),
            "size_bytes": sum((self.root / name).stat().st_size for name, _size, _sha in FILES if (self.root / name).exists()),
            "capabilities": ["text", "vision"],
            "languages": ["zh-CN", "en"],
            "estimated_peak_rss_bytes": 3097571328,
        })
        if not data["installed"] and data["state"] == "ready":
            data["state"] = "missing"
        if data["error"]:
            data["error"] = "本地视觉模型安装或启动失败；请重试并检查资源与网络"
        return data

    async def _download(self, force=False):
        temporary = None
        try:
            self._runtime.update(state="downloading", total_bytes=sum(size for _name, size, _sha in FILES), downloaded_bytes=0, error=None)
            for name, size, sha in FILES:
                target = self.root / name
                if target.exists() and not force and target.stat().st_size == size and await asyncio.to_thread(asset_digest, target) == sha:
                    self._runtime["downloaded_bytes"] += size
                    continue
                fd, temporary = tempfile.mkstemp(prefix="qwen-vision-", suffix=".download", dir=self.root)
                os.close(fd)
                timeout = aiohttp.ClientTimeout(total=3600, connect=30, sock_read=90)
                downloaded = False
                for host in ("huggingface.co", "hf-mirror.com"):
                    self._runtime["downloaded_bytes"] = sum((self.root / file).stat().st_size for file, _size, _sha in FILES if (self.root / file).is_file() and file != name)
                    try:
                        async with self.session_factory(timeout=timeout, trust_env=True) as session:
                            url = f"https://{host}/{REPOSITORY}/resolve/{REVISION}/{name}"
                            async with session.get(url) as response:
                                if response.status != 200:
                                    raise RuntimeError("visual asset download failed")
                                written = 0
                                with open(temporary, "wb") as output:
                                    async for chunk in response.content.iter_chunked(1024 * 1024):
                                        written += len(chunk)
                                        if written > size:
                                            raise RuntimeError("visual asset size mismatch")
                                        output.write(chunk)
                                        self._runtime["downloaded_bytes"] += len(chunk)
                        if written != size or await asyncio.to_thread(asset_digest, Path(temporary)) != sha:
                            raise RuntimeError("visual asset integrity check failed")
                        downloaded = True
                        break
                    except (aiohttp.ClientError, asyncio.TimeoutError, OSError, RuntimeError):
                        continue
                if not downloaded:
                    raise RuntimeError("visual asset download or integrity validation failed")
                os.replace(temporary, target)
                temporary = None
            self._save_metadata({"model_id": ASSET_ID, "revision": REVISION, "installed_at": utc_now(), "files": [name for name, _size, _sha in FILES]})
            self._runtime.update(state="ready", error=None)
        except asyncio.CancelledError:
            self._runtime.update(state="cancelled", error="Model download cancelled")
            raise
        except Exception:
            self._runtime.update(state="error", error="Visual model download or validation failed")
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)

    async def _setup(self, force=False):
        try:
            await self._download(force=force)
            if self._runtime["state"] != "ready":
                return
            await super()._setup(force=False)
        except asyncio.CancelledError:
            await self.stop_runtime()
            self._runtime.update(state="cancelled")
            raise

    def _validate_model_install(self):
        if not self._complete():
            raise RuntimeError("Install both the visual model and matching mmproj first")
        for name, _size, sha in FILES:
            if asset_digest(self.root / name) != sha:
                raise RuntimeError("Visual model integrity check failed")

    def _runtime_extra_arguments(self):
        return ["--mmproj", str(self.mmproj_path), "--no-mmproj-offload", "-ngl", "0", "-t", "4", "-tb", "4", "--parallel", "1", "-c", "4096"]

    async def start_runtime(self):
        data = await super().start_runtime()
        config = self.unified_config_store.load()
        previous = next((item for item in config["profiles"] if item["id"] == ASSET_ID), {})
        profiles = [item for item in config["profiles"] if item["id"] != ASSET_ID]
        profiles.append({
            "id": ASSET_ID,
            "name": previous.get("name", "Qwen3-VL-2B 本地视觉兜底"),
            "source": "managed-local",
            "endpoint": self.upstream_endpoint(),
            "model": FILES[0][0],
            "asset_id": ASSET_ID,
            "revision": REVISION,
            "capabilities": ["text", "vision"],
            "languages": ["zh-CN", "en"],
            "enabled": previous.get("enabled", True),
            "ready": True,
            "metadata": previous.get("metadata", {}),
        })
        self.unified_config_store.save({"profiles": profiles})
        return data

    async def stop_runtime(self):
        data = await super().stop_runtime()
        config = self.unified_config_store.load()
        changed = False
        for item in config["profiles"]:
            if item["id"] == ASSET_ID:
                item["ready"] = False
                changed = True
        if changed:
            self.unified_config_store.save({"profiles": config["profiles"]})
        return data

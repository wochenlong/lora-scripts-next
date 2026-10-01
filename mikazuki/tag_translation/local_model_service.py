"""Optional, user-managed local Qwen/llama.cpp runtime.

The translation feature never imports torch or starts a process implicitly.  This
small manager only owns the downloadable GGUF asset and, when the user supplies
an installed llama-server executable, its lifecycle.  The actual translation
client continues to use the OpenAI-compatible endpoint configured in
``translation.json``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import aiohttp


LOGGER = logging.getLogger(__name__)
MODEL_ID = "qwen3.5-0.8b-q4_0"
MODEL_FILENAME = "Qwen3.5-0.8B-Q4_0.gguf"
MODEL_URL = (
    "https://huggingface.co/ggml-org/Qwen3.5-0.8B-GGUF/resolve/main/"
    f"{MODEL_FILENAME}"
)
ALLOWED_HOSTS = {"huggingface.co", "hf.co", "cdn-lfs.huggingface.co"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class LocalModelService:
    def __init__(self, root: str | Path, config_store):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.root / "local-model.json"
        self.model_path = self.root / MODEL_FILENAME
        self.config_store = config_store
        self.session_factory = aiohttp.ClientSession
        self._task: asyncio.Task | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._runtime = {
            "state": "ready" if self.model_path.exists() else "missing",
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "error": None,
        }

    def status(self):
        config = self.config_store.load().get("local", {})
        state = self._runtime["state"]
        if self._process and self._process.returncode is None:
            state = "running"
        elif state not in {"downloading", "checking", "error", "cancelled"}:
            state = "ready" if self.model_path.exists() else "missing"
        return {
            "model_id": MODEL_ID,
            "model_filename": MODEL_FILENAME,
            "model_url": MODEL_URL,
            "model_path": str(self.model_path),
            "state": state,
            "installed": self.model_path.exists(),
            "size_bytes": self.model_path.stat().st_size if self.model_path.exists() else 0,
            "downloaded_bytes": self._runtime["downloaded_bytes"],
            "total_bytes": self._runtime["total_bytes"],
            "runtime_path": config.get("runtime_path", ""),
            "endpoint": config.get("endpoint", "http://127.0.0.1:8081/v1/chat/completions"),
            "port": int(config.get("port", 8081)),
            "error": self._runtime["error"],
        }

    def start_download(self, force=False):
        if self._task and not self._task.done():
            return self.status()
        self._runtime.update(state="downloading", downloaded_bytes=0, total_bytes=0, error=None)
        LOGGER.info("local tag translation model download queued: %s", MODEL_ID)
        self._task = asyncio.create_task(self._download(force=force))
        return self.status()

    def cancel_download(self):
        if self._task and not self._task.done():
            self._task.cancel()
            self._runtime.update(state="cancelled", error="Model download cancelled")
            LOGGER.info("local tag translation model download cancelled")
        return self.status()

    async def wait(self):
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        return self.status()

    async def _download(self, force=False):
        temporary = None
        try:
            if self.model_path.exists() and not force:
                self._runtime["state"] = "ready"
                return
            if urlparse(MODEL_URL).hostname not in ALLOWED_HOSTS:
                raise RuntimeError("Model download URL is not trusted")
            fd, temporary = tempfile.mkstemp(prefix="qwen-", suffix=".gguf.download", dir=self.root)
            os.close(fd)
            timeout = aiohttp.ClientTimeout(total=3600)
            async with self.session_factory(timeout=timeout, trust_env=True) as session:
                async with session.get(MODEL_URL, headers={"Accept": "application/octet-stream"}) as response:
                    if response.status != 200:
                        raise RuntimeError(f"Model download returned HTTP {response.status}")
                    self._runtime["total_bytes"] = int(response.headers.get("Content-Length") or 0)
                    with open(temporary, "wb") as target:
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            target.write(chunk)
                            self._runtime["downloaded_bytes"] += len(chunk)
            with open(temporary, "rb") as source:
                if source.read(4) != b"GGUF":
                    raise RuntimeError("Downloaded model is not a GGUF file")
            os.replace(temporary, self.model_path)
            temporary = None
            self._save_metadata({"model_id": MODEL_ID, "installed_at": utc_now(), "source": MODEL_URL})
            self._runtime.update(state="ready", error=None)
            LOGGER.info("local tag translation model ready: %s", self.model_path)
        except asyncio.CancelledError:
            self._runtime.update(state="cancelled", error="Model download cancelled")
            raise
        except Exception as error:
            self._runtime.update(state="error", error=str(error)[:1000])
            LOGGER.error("local tag translation model download failed: %s", error)
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.remove(temporary)
                except OSError:
                    pass

    async def start_runtime(self):
        if self._process and self._process.returncode is None:
            return self.status()
        config = self.config_store.load().get("local", {})
        executable = str(config.get("runtime_path") or "").strip()
        if not executable:
            raise RuntimeError("Configure the llama-server executable path first")
        if not self.model_path.exists():
            raise RuntimeError("Install the Qwen GGUF model first")
        if not os.path.isfile(executable):
            raise RuntimeError("The configured llama-server executable does not exist")
        port = int(config.get("port", 8081))
        command = [
            executable,
            "-m", str(self.model_path),
            "--host", "127.0.0.1",
            "--port", str(port),
            "-c", str(int(config.get("context_length", 2048))),
        ]
        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        LOGGER.info("local tag translation runtime started: pid=%s port=%s", self._process.pid, port)
        return self.status()

    def set_error(self, error):
        self._runtime.update(state="error", error=str(error)[:1000])
        LOGGER.error("local tag translation runtime error: %s", error)
        return self.status()

    async def stop_runtime(self):
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            LOGGER.info("local tag translation runtime stopped")
        self._process = None
        return self.status()

    def _save_metadata(self, payload):
        fd, temporary = tempfile.mkstemp(prefix="local-model-", suffix=".json.tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as target:
                json.dump(payload, target, ensure_ascii=False, indent=2)
                target.write("\n")
            os.replace(temporary, self.metadata_path)
        except Exception:
            if os.path.exists(temporary):
                os.remove(temporary)
            raise

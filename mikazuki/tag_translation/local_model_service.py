"""Managed local Qwen/llama.cpp runtime for tag translation.

The service owns the downloadable GGUF asset, the pinned llama.cpp runtime,
and the lifecycle of the internal OpenAI-compatible loopback endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import socket
import tempfile
import zipfile
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
MODEL_MIRROR_URL = (
    "https://hf-mirror.com/ggml-org/Qwen3.5-0.8B-GGUF/resolve/main/"
    f"{MODEL_FILENAME}"
)
RUNTIME_RELEASE_TAG = "b11327"
RUNTIME_ASSET_NAME = f"llama-{RUNTIME_RELEASE_TAG}-bin-win-cpu-x64.zip"
RUNTIME_SOURCE_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/"
    f"{RUNTIME_RELEASE_TAG}/{RUNTIME_ASSET_NAME}"
)
ALLOWED_HOSTS = {"huggingface.co", "hf-mirror.com", "hf.co", "cdn-lfs.huggingface.co"}
RUNTIME_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "ghfast.top",
    "ghproxy.net",
    "gh-proxy.com",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class LocalModelService:
    def __init__(self, root: str | Path, config_store):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.root / "local-model.json"
        self.model_path = self.root / MODEL_FILENAME
        self.runtime_root = self.root / "llama-runtime"
        self.runtime_executable = self.runtime_root / ("llama-server.exe" if os.name == "nt" else "llama-server")
        self.config_store = config_store
        self.session_factory = aiohttp.ClientSession
        self._task: asyncio.Task | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task | None = None
        self._stderr_tail = ""
        self._runtime_port: int | None = None
        self._runtime = {
            "state": "ready" if self.model_path.exists() else "missing",
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "error": None,
        }
        self._runtime_install = {
            "state": "ready" if self.runtime_executable.exists() else "missing",
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "error": None,
        }

    def status(self):
        config = self.config_store.load().get("local", {})
        state = self._runtime["state"]
        if self._task and not self._task.done() and self._runtime_install["state"] == "installing":
            state = "installing"
        if self._runtime_install["state"] == "error" and not self._process:
            state = "error"
        if self._process and self._process.returncode is None:
            state = "running"
        elif state not in {"downloading", "checking", "error", "cancelled"}:
            state = "ready" if self.model_path.exists() else "missing"
        return {
            "model_id": MODEL_ID,
            "runtime_version": RUNTIME_RELEASE_TAG,
            "model_filename": MODEL_FILENAME,
            "model_url": MODEL_URL,
            "model_path": str(self.model_path),
            "state": state,
            "installed": self.model_path.exists(),
            "size_bytes": self.model_path.stat().st_size if self.model_path.exists() else 0,
            "downloaded_bytes": self._runtime["downloaded_bytes"],
            "total_bytes": self._runtime["total_bytes"],
            "runtime_path": config.get("runtime_path", ""),
            "runtime_installed": self.runtime_executable.exists(),
            "runtime_state": self._runtime_install["state"],
            "runtime_downloaded_bytes": self._runtime_install["downloaded_bytes"],
            "runtime_total_bytes": self._runtime_install["total_bytes"],
            "endpoint": config.get("endpoint", "internal://dataset-translation"),
            "port": self._runtime_port or 0,
            "error": self._runtime["error"] or self._runtime_install["error"],
        }

    def upstream_endpoint(self):
        if not self._runtime_port:
            return ""
        return f"http://127.0.0.1:{self._runtime_port}/v1/chat/completions"

    @staticmethod
    def _allocate_loopback_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])

    def start_download(self, force=False):
        if self._task and not self._task.done():
            return self.status()
        self._runtime.update(state="downloading", downloaded_bytes=0, total_bytes=0, error=None)
        LOGGER.info("local tag translation model download queued: %s", MODEL_ID)
        self._task = asyncio.create_task(self._download(force=force))
        return self.status()

    def start_setup(self, force=False):
        if self._task and not self._task.done():
            return self.status()
        self._runtime.update(state="installing", downloaded_bytes=0, total_bytes=0, error=None)
        self._runtime_install.update(state="installing", downloaded_bytes=0, total_bytes=0, error=None)
        self._task = asyncio.create_task(self._setup(force=force))
        LOGGER.info("local tag translation runtime setup queued")
        return self.status()

    def cancel_download(self):
        if self._task and not self._task.done():
            self._task.cancel()
            self._runtime.update(state="cancelled", error="Model download cancelled")
            self._runtime_install.update(state="cancelled", error="Local runtime setup cancelled")
            LOGGER.info("local tag translation model download cancelled")
        return self.status()

    async def _setup(self, force=False):
        try:
            if not self.model_path.exists() or force:
                await self._download(force=force)
            if self._runtime["state"] == "error":
                return
            if not self.runtime_executable.exists() or force:
                await self._download_runtime(force=force)
            elif self._runtime_install["state"] != "ready":
                # A setup request may arrive after a process restart while the
                # runtime files are already present.  Reconcile the persisted
                # filesystem state before deciding whether setup is complete;
                # otherwise the UI remains stuck at "installing" forever.
                self._runtime_install.update(state="ready", error=None)
            if self._runtime_install["state"] == "ready":
                config = self.config_store.load()
                if not config.get("local", {}).get("runtime_path"):
                    self.config_store.save({"local": {"runtime_path": str(self.runtime_executable)}})
                self._runtime["state"] = "ready"
                try:
                    await self.start_runtime()
                except Exception as error:
                    self._runtime["state"] = "error"
                    self._runtime["error"] = str(error)[:1000]
                    LOGGER.warning("local runtime installed but could not start automatically: %s", error)
        except asyncio.CancelledError:
            self._runtime.update(state="cancelled", error="Local runtime setup cancelled")
            self._runtime_install.update(state="cancelled", error="Local runtime setup cancelled")
            raise
        except Exception as error:
            self._runtime.update(state="error", error=str(error)[:1000])
            self._runtime_install.update(state="error", error=str(error)[:1000])
            LOGGER.error("local tag translation runtime setup failed: %s", error)

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
            fd, temporary = tempfile.mkstemp(prefix="qwen-", suffix=".gguf.download", dir=self.root)
            os.close(fd)
            timeout = aiohttp.ClientTimeout(total=3600, connect=20, sock_connect=20, sock_read=60)
            errors = []
            downloaded = False
            for url in (MODEL_MIRROR_URL, MODEL_URL):
                if urlparse(url).hostname not in ALLOWED_HOSTS:
                    continue
                try:
                    async with self.session_factory(timeout=timeout, trust_env=True) as session:
                        async with session.get(url, headers={"Accept": "application/octet-stream"}) as response:
                            if response.status != 200:
                                raise RuntimeError(f"HTTP {response.status}")
                            self._runtime["total_bytes"] = int(response.headers.get("Content-Length") or 0)
                            with open(temporary, "wb") as target:
                                async for chunk in response.content.iter_chunked(1024 * 1024):
                                    target.write(chunk)
                                    self._runtime["downloaded_bytes"] += len(chunk)
                    LOGGER.info("local tag translation model downloaded from %s", urlparse(url).hostname)
                    downloaded = True
                    break
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError, RuntimeError) as error:
                    errors.append(f"{urlparse(url).hostname}: {error}")
                    self._runtime["downloaded_bytes"] = 0
                    try:
                        os.remove(temporary)
                    except OSError:
                        pass
            if not downloaded:
                raise RuntimeError("Model download failed; " + " | ".join(errors))
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

    async def _download_runtime(self, force=False):
        temporary = None
        try:
            if platform.system() != "Windows":
                raise RuntimeError("Automatic llama.cpp setup currently supports Windows")
            fd, temporary = tempfile.mkstemp(prefix="llama-", suffix=".zip.download", dir=self.root)
            os.close(fd)
            mirror_urls = [
                f"https://{mirror}/{RUNTIME_SOURCE_URL}"
                for mirror in ("ghfast.top", "ghproxy.net", "gh-proxy.com")
            ]
            errors = []
            downloaded = False
            timeout = aiohttp.ClientTimeout(total=1800, connect=20, sock_connect=20, sock_read=60)
            for url in (*mirror_urls, RUNTIME_SOURCE_URL):
                if urlparse(url).hostname not in RUNTIME_HOSTS:
                    continue
                try:
                    async with self.session_factory(timeout=timeout, trust_env=True) as session:
                        async with session.get(url, headers={"Accept": "application/octet-stream"}) as response:
                            if response.status != 200:
                                raise RuntimeError(f"HTTP {response.status}")
                            self._runtime_install["total_bytes"] = int(response.headers.get("Content-Length") or 0)
                            with open(temporary, "wb") as target:
                                async for chunk in response.content.iter_chunked(1024 * 1024):
                                    target.write(chunk)
                                    self._runtime_install["downloaded_bytes"] += len(chunk)
                    LOGGER.info("llama.cpp runtime downloaded from %s", urlparse(url).hostname)
                    downloaded = True
                    break
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError, RuntimeError) as error:
                    errors.append(f"{urlparse(url).hostname}: {error}")
                    self._runtime_install["downloaded_bytes"] = 0
                    try:
                        os.remove(temporary)
                    except OSError:
                        pass
            if not downloaded:
                raise RuntimeError("llama.cpp runtime download failed; " + " | ".join(errors))
            self.runtime_root.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(temporary) as archive:
                members = archive.infolist()
                server_members = [
                    item for item in members
                    if Path(item.filename).name.lower() == self.runtime_executable.name.lower()
                ]
                if not server_members:
                    raise RuntimeError("llama.cpp archive does not contain llama-server")
                root = self.runtime_root.resolve()
                for member in members:
                    target = (self.runtime_root / member.filename).resolve()
                    if target != root and root not in target.parents:
                        raise RuntimeError("llama.cpp archive contains an unsafe path")
                archive.extractall(self.runtime_root)
                extracted = next(
                    (self.runtime_root / member.filename).resolve()
                    for member in server_members
                )
                self.runtime_executable = extracted
            if not self.runtime_executable.exists() or self.runtime_executable.stat().st_size < 1024:
                raise RuntimeError("llama-server installation is incomplete")
            if os.name != "nt":
                self.runtime_executable.chmod(0o755)
            self._runtime_install.update(state="ready", error=None)
            LOGGER.info("llama.cpp runtime ready: %s", self.runtime_executable)
        except asyncio.CancelledError:
            self._runtime_install.update(state="cancelled", error="Runtime download cancelled")
            raise
        except Exception as error:
            self._runtime_install.update(state="error", error=str(error)[:1000])
            LOGGER.error("llama.cpp runtime download failed: %s", error)
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
        executable = str(config.get("runtime_path") or self.runtime_executable).strip()
        if not self.model_path.exists():
            raise RuntimeError("Install the Qwen GGUF model first")
        if not os.path.isfile(executable):
            raise RuntimeError("The configured llama-server executable does not exist")
        port = self._allocate_loopback_port()
        self._runtime_port = port
        command = [
            executable,
            "-m", str(self.model_path),
            "--host", "127.0.0.1",
            "--port", str(port),
            "-c", str(int(config.get("context_length", 2048))),
            # Qwen3.5 defaults to a reasoning trace.  Tag translation needs a
            # short structured answer, so force non-thinking mode at the
            # managed server level instead of relying on provider-specific
            # request fields.
            "--reasoning", "off",
            "--reasoning-budget", "0",
            "--chat-template-kwargs", '{"enable_thinking":false}',
        ]
        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._stderr_tail = ""
        self._stderr_task = asyncio.create_task(self._drain_stderr(self._process.stderr))
        ready = False
        timeout = aiohttp.ClientTimeout(total=1)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
            # Loading a GGUF model can take tens of seconds on a CPU-only
            # machine.  Keep the process alive long enough for a first-run
            # install instead of killing a healthy server during model load.
            for _ in range(300):
                if self._process.returncode is not None:
                    detail = self._stderr_tail.strip()
                    await self.stop_runtime()
                    suffix = f": {detail[-800:]}" if detail else ""
                    raise RuntimeError(f"llama-server exited before becoming healthy{suffix}")
                try:
                    async with session.get(f"http://127.0.0.1:{port}/health") as response:
                        if response.status == 200:
                            ready = True
                            break
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    pass
                await asyncio.sleep(0.2)
        if not ready:
            detail = self._stderr_tail.strip()
            await self.stop_runtime()
            suffix = f": {detail[-800:]}" if detail else ""
            raise RuntimeError(f"llama-server did not become healthy on the managed loopback port{suffix}")
        self._runtime.update(state="ready", error=None)
        LOGGER.info("local tag translation runtime started: pid=%s port=%s", self._process.pid, port)
        return self.status()

    async def _drain_stderr(self, stream):
        if stream is None:
            return
        try:
            while True:
                chunk = await stream.readline()
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace").strip()
                if text:
                    self._stderr_tail = (self._stderr_tail + "\n" + text)[-4000:]
        except (asyncio.CancelledError, OSError):
            return

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
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
        self._stderr_task = None
        self._process = None
        self._runtime_port = None
        if self.model_path.exists() and self._runtime["state"] == "error":
            self._runtime.update(state="ready", error=None)
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

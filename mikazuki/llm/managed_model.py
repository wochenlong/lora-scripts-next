"""Qwen3.5 图文资产和进程唯一管理器；不消费旧 local 配置。"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import shutil
import socket
import stat
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

import aiohttp
from PIL import Image

from . import model_manifest as locked
from .client import build_chat_payload, parse_json_content
from .config import config_revision, configuration_lock
from .contracts import LLMConfigConflict, LLMContractError, LLMProfile
from .http import LLMRequestError, chat_completion
from .scheduler import shared_local_scheduler


def asset_digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def safe_path(path, root=None):
    path = Path(path).absolute()
    if root is not None:
        path.relative_to(Path(root).absolute())
        path.resolve().relative_to(Path(root).resolve())
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            if item.is_symlink() or getattr(item.lstat(), "st_file_attributes", 0) & 0x400:
                raise RuntimeError("managed_asset_path_unsafe")
    return path


def write_json(path, value):
    safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".managed-", suffix=".json.tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, ensure_ascii=False, sort_keys=True, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class ManagedModelService:
    def __init__(self, translation_root, unified_config_store, *, files=None, scheduler=None):
        self.translation_root = safe_path(translation_root)
        self.root = self.translation_root / "models" / locked.ASSET_ID / locked.REVISION
        safe_path(self.root, self.translation_root).mkdir(parents=True, exist_ok=True)
        self.files = tuple(files or locked.FILES)
        self.model_path = self.root / self.files[0][0]
        self.mmproj_path = self.root / self.files[1][0]
        self.metadata_path = self.root / "local-model.json"
        self.runtime_root = self.translation_root / "models" / "llama-runtime" / locked.RUNTIME_VERSION / locked.RUNTIME_SHA256[:16]
        self.archive_path = self.runtime_root.parent / locked.RUNTIME_FILENAME
        self.runtime_executable = self.runtime_root / "llama-server.exe"
        self.unified_config_store = self.config_store = unified_config_store
        self.session_factory = aiohttp.ClientSession
        self.scheduler = scheduler or shared_local_scheduler
        self._state_lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._task = self._task_loop = self._process = self._process_loop = self._stderr_task = None
        self._stderr_tail = ""
        self._runtime_port = None
        self._verified = self._installed_verified = self._runtime_verified = False
        self._file_signatures = None
        self._runtime = {"state": "missing", "downloaded_bytes": 0, "total_bytes": sum(item[1] for item in self.files), "error": None}
        self._runtime_install = {"state": "missing", "downloaded_bytes": 0, "total_bytes": locked.RUNTIME_SIZE, "error": None}

    @contextmanager
    def _operation(self):
        if not self._operation_lock.acquire(blocking=False):
            raise LLMRequestError("本地模型生命周期操作正在进行", "llm_local_busy", retryable=True)
        try:
            yield
        finally:
            self._operation_lock.release()

    def _live(self):
        return self._process is not None and self._process.returncode is None

    def _signatures(self):
        result = []
        for name, _size, _sha in self.files:
            path = self.root / name
            if not path.is_file():
                return None
            value = path.stat()
            result.append((name, value.st_size, value.st_mtime_ns, value.st_ctime_ns))
        return tuple(result)

    def status(self):
        with self._state_lock:
            if not self._live():
                self._verified = False
            if self._installed_verified and self._signatures() != self._file_signatures:
                self._installed_verified = self._verified = False
            state = self._runtime["state"]
            if self._live():
                state = "running" if self._verified else "checking"
            elif state == "running":
                state = "error"
            return {
                "model_id": locked.ASSET_ID, "asset_id": locked.ASSET_ID, "revision": locked.REVISION,
                "runtime_version": locked.RUNTIME_VERSION, "model_filename": self.files[0][0],
                "model_url": f"https://huggingface.co/{locked.REPOSITORY}/resolve/{locked.REVISION}/{self.files[0][0]}",
                "model_path": str(self.model_path), "mmproj_path": str(self.mmproj_path),
                "state": state, "ready": self._verified and self._live(), "installed": self._installed_verified,
                "size_bytes": sum((self.root / name).stat().st_size for name, _, _ in self.files if (self.root / name).is_file()),
                "downloaded_bytes": self._runtime["downloaded_bytes"], "total_bytes": self._runtime["total_bytes"],
                "runtime_path": str(self.runtime_executable), "runtime_installed": self._runtime_verified,
                "runtime_state": self._runtime_install["state"], "runtime_downloaded_bytes": self._runtime_install["downloaded_bytes"],
                "runtime_total_bytes": self._runtime_install["total_bytes"], "endpoint": self.upstream_endpoint(),
                "port": self._runtime_port or 0, "pid": self._process.pid if self._live() else None,
                "capabilities": list(locked.CAPABILITIES), "languages": list(locked.LANGUAGES),
                "estimated_peak_rss_bytes": None, "supported": locked.platform_supported(),
                "queue": self.scheduler.snapshot(), "error": self._runtime["error"] or self._runtime_install["error"],
            }

    def upstream_endpoint(self):
        return f"http://127.0.0.1:{self._runtime_port}/v1/chat/completions" if self._runtime_port else ""

    @staticmethod
    def _allocate_loopback_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    def _require_platform(self):
        if not locked.platform_supported():
            raise LLMRequestError("当前一键本地模型支持 Windows x64 CPU；其它平台可配置自己的兼容接口", "llm_local_platform_unsupported")

    def _ensure_space(self, needed):
        if shutil.disk_usage(self.root).free < needed + 256 * 1024**2:
            raise LLMRequestError("磁盘空间不足，无法安全安装本地模型", "llm_local_disk_space")

    def _validate_model_install(self):
        for name, size, sha in self.files:
            path = safe_path(self.root / name, self.root)
            if not path.is_file() or path.stat().st_size != size or asset_digest(path) != sha:
                self._installed_verified = False
                raise RuntimeError("managed_model_integrity_failed")
        self._file_signatures = self._signatures()
        self._installed_verified = True

    async def _fetch_file(self, target, size, sha, urls, progress):
        safe_path(target, self.translation_root).parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and target.stat().st_size == size and await asyncio.to_thread(asset_digest, target) == sha:
            progress["downloaded_bytes"] += size
            return
        self._ensure_space(size)
        fd, temporary = tempfile.mkstemp(prefix=".qwen-", suffix=".download", dir=target.parent)
        os.close(fd)
        prior = progress["downloaded_bytes"]
        try:
            for url in list(dict.fromkeys(urls))[:3]:
                progress["downloaded_bytes"] = prior
                try:
                    timeout = aiohttp.ClientTimeout(total=3600, connect=30, sock_read=90)
                    async with self.session_factory(timeout=timeout, trust_env=True) as session:
                        async with session.get(url, headers={"Accept-Encoding": "identity"}) as response:
                            if response.status != 200:
                                raise RuntimeError("managed_download_http_failed")
                            count, value = 0, hashlib.sha256()
                            with open(temporary, "wb") as output:
                                async for block in response.content.iter_chunked(1024 * 1024):
                                    count += len(block)
                                    if count > size:
                                        raise RuntimeError("managed_download_size_failed")
                                    output.write(block)
                                    value.update(block)
                                    progress["downloaded_bytes"] = prior + count
                                output.flush()
                                os.fsync(output.fileno())
                    if count != size or value.hexdigest() != sha:
                        raise RuntimeError("managed_download_integrity_failed")
                    os.replace(temporary, target)
                    return
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError, RuntimeError):
                    continue
            raise RuntimeError("managed_download_validation_failed")
        finally:
            Path(temporary).unlink(missing_ok=True)

    async def _download_assets(self):
        self._runtime.update(state="downloading", downloaded_bytes=0, error=None)
        configured = (os.environ.get("HF_ENDPOINT") or "").rstrip("/")
        mirrors = [configured] if configured in {"https://huggingface.co", "https://hf-mirror.com"} else []
        mirrors.extend(["https://huggingface.co", "https://hf-mirror.com"])
        for name, size, sha in self.files:
            await self._fetch_file(self.root / name, size, sha, [f"{host}/{locked.REPOSITORY}/resolve/{locked.REVISION}/{name}" for host in mirrors], self._runtime)
        await asyncio.to_thread(self._validate_model_install)
        write_json(self.metadata_path, {"asset_id": locked.ASSET_ID, "revision": locked.REVISION,
                                       "files": [{"name": name, "size_bytes": size, "sha256": sha} for name, size, sha in self.files]})
        self._runtime.update(state="ready", error=None)

    def _archive_inventory(self):
        if not self.archive_path.is_file() or self.archive_path.stat().st_size != locked.RUNTIME_SIZE or asset_digest(self.archive_path) != locked.RUNTIME_SHA256:
            raise RuntimeError("managed_runtime_archive_integrity_failed")
        inventory = {}
        with zipfile.ZipFile(self.archive_path) as archive:
            members = archive.infolist()
            if len(members) > 5000 or sum(item.file_size for item in members) > 2 * 1024**3:
                raise RuntimeError("managed_runtime_archive_bounds_failed")
            names = set()
            reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
            for member in members:
                path = PurePosixPath(member.filename.replace("\\", "/"))
                if path.is_absolute() or not path.parts or any(part in {"..", "."} or ":" in part or part.endswith((".", " ")) or part.split(".")[0].upper() in reserved for part in path.parts):
                    raise RuntimeError("managed_runtime_archive_path_failed")
                portable = path.as_posix().casefold()
                if portable in names or stat.S_ISLNK(member.external_attr >> 16):
                    raise RuntimeError("managed_runtime_archive_duplicate_or_symlink")
                names.add(portable)
                if member.is_dir():
                    continue
                value = hashlib.sha256()
                with archive.open(member) as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        value.update(block)
                inventory[path.as_posix()] = {"size_bytes": member.file_size, "sha256": value.hexdigest(), "archive_name": member.filename}
        executable = [name for name in inventory if PurePosixPath(name).name.lower() == "llama-server.exe"]
        if len(executable) != 1 or inventory[executable[0]]["sha256"] != locked.EXECUTABLE_SHA256:
            raise RuntimeError("managed_runtime_executable_integrity_failed")
        return inventory, executable[0]

    def _validate_runtime_install(self):
        inventory, executable = self._archive_inventory()
        receipt = safe_path(self.runtime_root / "runtime-package.json", self.translation_root)
        if not receipt.is_file() or json.loads(receipt.read_text(encoding="utf-8")) != {"version": locked.RUNTIME_VERSION, "archive_sha256": locked.RUNTIME_SHA256, "files": inventory}:
            self._runtime_verified = False
            raise RuntimeError("managed_runtime_receipt_integrity_failed")
        actual = {item.relative_to(self.runtime_root).as_posix() for item in self.runtime_root.rglob("*") if item.is_file() and item != receipt}
        if actual != set(inventory):
            raise RuntimeError("managed_runtime_inventory_mismatch")
        for name, expected in inventory.items():
            path = safe_path(self.runtime_root / name, self.runtime_root)
            if not path.is_file() or path.stat().st_size != expected["size_bytes"] or asset_digest(path) != expected["sha256"]:
                self._runtime_verified = False
                raise RuntimeError("managed_runtime_file_integrity_failed")
        self.runtime_executable = self.runtime_root / executable
        self._runtime_verified = True
        self._runtime_install["state"] = "ready"

    def _extract_runtime(self):
        inventory, executable = self._archive_inventory()
        if self.runtime_root.exists():
            try:
                self._validate_runtime_install()
                return
            except (RuntimeError, OSError, ValueError):
                safe_path(self.runtime_root, self.translation_root)
                self.runtime_root.rename(self.runtime_root.with_name(self.runtime_root.name + ".invalid-" + uuid.uuid4().hex))
        staging = self.runtime_root.with_name(self.runtime_root.name + ".extract-" + uuid.uuid4().hex)
        safe_path(staging, self.translation_root).mkdir(parents=True)
        try:
            self._ensure_space(sum(item["size_bytes"] for item in inventory.values()))
            with zipfile.ZipFile(self.archive_path) as archive:
                for name, expected in inventory.items():
                    path = safe_path(staging / name, staging)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(expected["archive_name"]) as source, path.open("xb") as target:
                        shutil.copyfileobj(source, target, 1024 * 1024)
            write_json(staging / "runtime-package.json", {"version": locked.RUNTIME_VERSION, "archive_sha256": locked.RUNTIME_SHA256, "files": inventory})
            staging.rename(self.runtime_root)
            self.runtime_executable = self.runtime_root / executable
            self._validate_runtime_install()
        finally:
            if staging.exists():
                safe_path(staging, self.translation_root)
                shutil.rmtree(staging)  # 仅本调用创建的管理根内临时提取目录。

    async def _download_runtime_assets(self):
        self._runtime_install.update(state="installing", downloaded_bytes=0, error=None)
        await self._fetch_file(self.archive_path, locked.RUNTIME_SIZE, locked.RUNTIME_SHA256,
                              [locked.RUNTIME_URL, "https://ghfast.top/" + locked.RUNTIME_URL, "https://ghproxy.net/" + locked.RUNTIME_URL], self._runtime_install)
        extraction = asyncio.create_task(asyncio.to_thread(self._extract_runtime))
        try:
            await asyncio.shield(extraction)
        except asyncio.CancelledError:
            # 文件系统提取不能中途遗留仍在写入的线程；等待本次有界提取收尾再释放操作锁。
            await extraction
            raise

    async def reconcile_installation(self):
        """应用启动时校验已有文件，不下载、不注册 ready、不自动启动。"""
        with self._operation():
            try:
                await asyncio.to_thread(self._validate_model_install)
                await asyncio.to_thread(self._validate_runtime_install)
                self._runtime.update(state="ready", error=None)
            except (RuntimeError, OSError, ValueError):
                self._runtime.update(state="missing", error=None)
            return self.status()

    def _queue_operation(self, setup):
        self._require_platform()
        with self._state_lock:
            if self._task and not self._task.done() or self._verified and self._live():
                return self.status()
            if not self._operation_lock.acquire(blocking=False):
                raise LLMRequestError("本地模型生命周期操作正在进行", "llm_local_busy", retryable=True)
            try:
                self._task_loop = asyncio.get_running_loop()
                self._runtime.update(state="installing" if setup else "downloading", error=None)
                # A failed setup stores an error in both download sections.
                # Clear both when a new operation is admitted so a retry's
                # live progress cannot display the previous attempt's error.
                self._runtime_install["error"] = None
                self._task = self._task_loop.create_task(self._background_install(setup))
            except BaseException:
                self._operation_lock.release()
                raise
        return self.status()

    def start_download(self, force=False):
        return self._queue_operation(False)

    def start_setup(self, force=False):
        return self._queue_operation(True)

    def cancel_download(self):
        with self._state_lock:
            if self._task and not self._task.done():
                self._runtime.update(state="cancelling", error=None)
                self._task_loop.call_soon_threadsafe(self._task.cancel)
        return self.status()

    async def wait(self):
        if self._task:
            if self._task.get_loop() is not asyncio.get_running_loop():
                raise RuntimeError("managed_install_wait_requires_owner_loop")
            await asyncio.gather(self._task, return_exceptions=True)
        return self.status()

    async def _install(self, setup):
        with self.scheduler.idle_guard():
            await self._download_assets()
            if setup:
                await self._download_runtime_assets()
                await self._start_unlocked()

    async def _background_install(self, setup):
        try:
            await self._install(setup)
        except asyncio.CancelledError:
            await self._stop_unlocked()
            self._runtime.update(state="cancelled", error=None)
            self._runtime_install.update(state="cancelled", error=None)
            raise
        except Exception as error:
            await self._stop_unlocked()
            self._runtime.update(state="error", error=getattr(error, "code", "llm_local_install_failed"))
            self._runtime_install["error"] = getattr(error, "code", "llm_local_install_failed")
        finally:
            self._operation_lock.release()

    async def _download(self, force=False):
        await self._manual_install(False)

    async def _setup(self, force=False):
        await self._manual_install(True)

    async def _manual_install(self, setup):
        with self._operation():
            try:
                self._require_platform()
                await self._install(setup)
            except asyncio.CancelledError:
                await self._stop_unlocked()
                self._runtime.update(state="cancelled", error=None)
                raise
            except Exception as error:
                await self._stop_unlocked()
                self._runtime.update(state="error", error=getattr(error, "code", "llm_local_install_failed"))

    def _runtime_extra_arguments(self):
        return ["--mmproj", str(self.mmproj_path), "--no-mmproj-offload", "-ngl", "0", "-t", "4", "-tb", "4", "--parallel", "1", "-c", "4096"]

    async def _drain_stderr(self):
        try:
            while self._process and self._process.stderr:
                block = await self._process.stderr.read(4096)
                if not block:
                    break
                self._stderr_tail = (self._stderr_tail + block.decode("utf-8", errors="replace"))[-4000:]
        except (asyncio.CancelledError, OSError):
            pass

    def _profile(self):
        return LLMProfile(id=locked.ASSET_ID, name="Qwen3.5-2B 本地共享模型", endpoint=self.upstream_endpoint(), model=locked.ASSET_ID,
                          source="managed-local", capabilities=locked.CAPABILITIES, languages=locked.LANGUAGES, asset_id=locked.ASSET_ID, revision=locked.REVISION)

    async def _diagnostics(self):
        profile = self._profile()

        def factory(**kwargs):
            kwargs["trust_env"] = False
            return self.session_factory(**kwargs)

        schema = {"type": "object", "properties": {"translation": {"type": "string", "minLength": 1, "maxLength": 80}, "language": {"type": "string", "enum": ["zh-CN"]}},
                  "required": ["translation", "language"], "additionalProperties": False}
        payload = build_chat_payload(profile, prompt='Translate "a red box" into Simplified Chinese. Return only JSON with translation and language; language must be "zh-CN".', response_schema=schema, max_tokens=128, temperature=0)
        envelope, content = await chat_completion(profile, payload, session_factory=factory, timeout_seconds=120, retries=0)
        text = parse_json_content(content)
        if envelope.get("choices", [{}])[0].get("finish_reason") == "length" or set(text) != {"translation", "language"} or text.get("language") != "zh-CN" or not isinstance(text.get("translation"), str) or "红" not in text["translation"] or not any(word in text["translation"] for word in ("盒", "箱")):
            raise RuntimeError("managed_text_diagnostic_failed")
        image = Image.new("RGB", (128, 128), "red")
        image.paste(Image.new("RGB", (64, 128), "blue"), (64, 0))
        output = io.BytesIO()
        image.save(output, format="PNG")
        url = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
        schema = {"type": "object", "properties": {"colors": {"type": "array", "items": {"type": "string", "enum": ["red", "blue", "green", "yellow"]}, "minItems": 2, "maxItems": 2}}, "required": ["colors"], "additionalProperties": False}
        payload = build_chat_payload(profile, prompt="Identify the two large visible colors in this image. Return only JSON with the colors key containing two English color names.", image_data_url=url, response_schema=schema, max_tokens=64, temperature=0)
        envelope, content = await chat_completion(profile, payload, session_factory=factory, timeout_seconds=120, retries=0)
        vision = parse_json_content(content)
        if envelope.get("choices", [{}])[0].get("finish_reason") == "length" or set(vision) != {"colors"} or not isinstance(vision["colors"], list) or len(vision["colors"]) != 2 or set(vision["colors"]) != {"red", "blue"}:
            raise RuntimeError("managed_vision_diagnostic_failed")
        return {"text": True, "vision": True}

    def _register_verified(self):
        with configuration_lock(self.unified_config_store.path):
            config = self.unified_config_store.load()
            previous = next((item for item in config["profiles"] if item["id"] == locked.ASSET_ID), {})
            profiles = [item for item in config["profiles"] if item["id"] != locked.ASSET_ID]
            profiles.append({"id": locked.ASSET_ID, "name": previous.get("name", "Qwen3.5-2B 本地共享模型"), "source": "managed-local",
                            "endpoint": self.upstream_endpoint(), "model": locked.ASSET_ID, "asset_id": locked.ASSET_ID, "revision": locked.REVISION,
                            "capabilities": list(locked.CAPABILITIES), "languages": list(locked.LANGUAGES), "enabled": previous.get("enabled", True),
                            "metadata": previous.get("metadata", {}), "ready": False})
            self.unified_config_store.save({"profiles": profiles})
            selected = next(item for item in self.unified_config_store.load()["profiles"] if item["id"] == locked.ASSET_ID)
            for capability in locked.CAPABILITIES:
                self.unified_config_store.record_verification(locked.ASSET_ID, config_revision(selected), capability, successful=True)

    def _invalidate(self):
        self._verified = False
        try:
            with configuration_lock(self.unified_config_store.path):
                profile = next((item for item in self.unified_config_store.load()["profiles"] if item["id"] == locked.ASSET_ID), None)
                if profile:
                    for capability in locked.CAPABILITIES:
                        self.unified_config_store.record_verification(locked.ASSET_ID, config_revision(profile), capability, successful=False)
        except (LLMConfigConflict, LLMContractError, OSError, ValueError):
            # Runtime cleanup remains authoritative even if a concurrent config
            # edit made the verification fingerprint stale.
            return

    async def _start_unlocked(self):
        self._require_platform()
        if self._verified and self._live():
            return self.status()
        self._invalidate()
        self._runtime.update(state="checking", error=None)
        await asyncio.to_thread(self._validate_model_install)
        await asyncio.to_thread(self._validate_runtime_install)
        self._runtime_port = self._allocate_loopback_port()
        command = [str(self.runtime_executable), "-m", str(self.model_path), "--alias", locked.ASSET_ID, "--host", "127.0.0.1", "--port", str(self._runtime_port),
                   "--jinja", "--reasoning", "off", "--reasoning-budget", "0", "--chat-template-kwargs", '{"enable_thinking":false}', "--slots"]
        command.extend(self._runtime_extra_arguments())
        self._process_loop = asyncio.get_running_loop()
        self._process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.PIPE, creationflags=0x08000000 if os.name == "nt" else 0)
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        deadline = time.perf_counter() + 120
        async with self.session_factory(timeout=aiohttp.ClientTimeout(total=1), trust_env=False) as session:
            while time.perf_counter() < deadline:
                if not self._live():
                    raise RuntimeError("managed_runtime_exited_before_health")
                try:
                    async with session.get(f"http://127.0.0.1:{self._runtime_port}/health") as response:
                        if response.status == 200:
                            break
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    pass
                await asyncio.sleep(.2)
            else:
                raise RuntimeError("managed_runtime_health_timeout")
        await self._diagnostics()
        if not self._live():
            raise RuntimeError("managed_runtime_exited_during_diagnostics")
        self._register_verified()
        self._verified = True
        self._runtime.update(state="running", error=None)
        return self.status()

    async def start_runtime(self):
        with self._operation():
            if self._verified and self._live():
                return self.status()
            with self.scheduler.idle_guard():
                try:
                    return await self._start_unlocked()
                except BaseException:
                    await self._stop_unlocked()
                    self._runtime.update(state="error", error="llm_local_start_failed")
                    raise

    async def _stop_unlocked(self):
        try:
            self._invalidate()
        finally:
            # 损坏配置也不得阻止释放本管理器启动的进程。
            if self._process and self._process.returncode is None:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), 5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            if self._stderr_task:
                self._stderr_task.cancel()
                await asyncio.gather(self._stderr_task, return_exceptions=True)
            self._stderr_task = self._process = None
            self._runtime_port = None
            self._runtime.update(state="ready" if self._installed_verified else "missing", error=None)
        return self.status()

    async def stop_runtime(self):
        with self._operation():
            with self.scheduler.idle_guard():
                return await self._stop_unlocked()

    async def shutdown(self):
        """应用退出专用：只取消自己的安装，等待调用者取消请求后清理自有进程。"""
        if self._task and not self._task.done():
            self.cancel_download()
            if self._task_loop is asyncio.get_running_loop():
                await asyncio.gather(self._task, return_exceptions=True)
            else:
                deadline = time.perf_counter() + 10
                while not self._task.done() and time.perf_counter() < deadline:
                    await asyncio.sleep(.05)
        deadline = time.perf_counter() + 10
        while self.scheduler.is_busy() and time.perf_counter() < deadline:
            await asyncio.sleep(.05)
        # shutdown 清理自己的进程不清空共享队列；活跃 socket 被终止后应自己释放。
        with self._operation():
            return await self._stop_unlocked()

    def set_error(self, error):
        self._runtime.update(state="error", error=getattr(error, "code", "llm_local_runtime_failed"))
        return self.status()

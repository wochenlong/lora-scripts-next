from __future__ import annotations

import hashlib
import asyncio
import json
import os
import tempfile
import threading
import time
import uuid
import copy
import sqlite3
from pathlib import Path
from typing import Literal
from mikazuki.tagger.progress import TaggerCancelled, tagger_progress
from .caption_write import caption_file_lock, locked_caption, recover_caption_write

CaptionConflict = Literal["ignore", "copy", "prepend", "append"]
_UNSET_HASH = object()
_AUTO_BRIDGE = object()


class CaptionWriteConflict(RuntimeError):
    code = "caption_conflict"


class CaptionJobCancelled(RuntimeError):
    code = "caption_cancelled"


class CaptionDatasetInUse(RuntimeError):
    code = "dataset_in_use"


class CaptionPersistenceError(RuntimeError):
    code = "caption_persistence_failed"


def safe_error_message(error):
    if isinstance(error, OSError):
        return "无法读取或写入图片及 caption 文件"
    if getattr(error, "code", None):
        return str(error)[:300]
    return "打标处理失败，请检查模型和任务参数"


def caption_path_for(image_path: Path) -> Path:
    return image_path.with_suffix(".txt")


def caption_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def merge_caption(existing: str, generated: str, action: CaptionConflict) -> tuple[str, bool]:
    generated = generated.strip()
    if action == "ignore":
        return existing, False
    if action == "copy":
        return generated, True
    if not existing.strip():
        return generated, True
    separator = "\n\n"
    if action == "prepend":
        return generated + separator + existing, True
    if action == "append":
        return existing + separator + generated, True
    raise ValueError(f"unknown caption conflict action: {action}")


@locked_caption
def write_caption_atomic(
    path: Path,
    caption: str,
    *,
    expected_sha256: str | None | object = _UNSET_HASH,
    trailing_newline: bool = True,
) -> str:
    current_sha256 = caption_sha256(path)
    if expected_sha256 is not _UNSET_HASH and current_sha256 != expected_sha256:
        raise CaptionWriteConflict("caption changed while the job was running")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as target:
            target.write(caption)
            if trailing_newline and not caption.endswith("\n"):
                target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        if expected_sha256 is not _UNSET_HASH and caption_sha256(path) != expected_sha256:
            raise CaptionWriteConflict("caption changed while the job was running")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return caption_sha256(path) or ""


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def discover_images(root: str | Path, recursive: bool = False) -> list[Path]:
    base = Path(root).expanduser()
    if not base.is_dir():
        raise FileNotFoundError("caption input path is not a directory")
    iterator = base.rglob("*") if recursive else base.glob("*")
    return sorted(
        (path for path in iterator if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda path: path.as_posix().casefold(),
    )


class CaptionJobManager:
    """Single active caption job with cooperative cancellation and retry support."""

    def __init__(self, service=None, cache=None, job_store=None, task_bridge=_AUTO_BRIDGE):
        self.service = service
        self.cache = cache
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._request: dict | None = None
        self._status: dict = self._idle()
        self._failed: list[dict] = []
        self._job_service = service
        if job_store is None and service is None:
            from mikazuki.llm.runtime import caption_job_store
            job_store = caption_job_store
        self.job_store = job_store
        if task_bridge is _AUTO_BRIDGE:
            if service is None:
                from .task_bridge import CaptionTaskBridge
                task_bridge = CaptionTaskBridge()
            else:
                task_bridge = None
        self.task_bridge = task_bridge
        self._paths: list[str] = []
        self._completed: list[int] = []
        self._intent: dict | None = None
        if self.job_store:
            self._recover()
        if self.task_bridge:
            self.task_bridge.restore(self.job_store)

    def _recover(self):
        # Pin the current task before repairing history. A failed older task
        # must not disappear merely because another task became the latest one.
        try:
            latest = self.job_store.get()
            jobs = self.job_store.all_jobs() if latest else []
        except (sqlite3.Error, OSError):
            raise CaptionPersistenceError("无法读取任务恢复记录，已阻止新任务，请检查数据库后重试") from None
        from .caption_maintenance import recover_prepared_rollbacks
        if not latest:
            recover_prepared_rollbacks(self.job_store)
            return
        latest_id = latest["state"]["job_id"]
        for saved in jobs:
            state, recovery = saved["state"], saved["recovery"]
            incomplete_error = state["phase"] == "error" and len(set(recovery["completed"])) < len(recovery["paths"])
            if recovery.get("intent") or state["phase"] in {"pending", "captioning", "cancelling"} or incomplete_error:
                saved = self._recover_saved_job(saved)
            if state["job_id"] == latest_id:
                latest = saved
        recover_prepared_rollbacks(self.job_store)
        self._status = copy.deepcopy(latest["state"])
        recovery = latest["recovery"]
        self._request = copy.deepcopy(recovery["request"])
        self._paths = list(recovery["paths"])
        self._completed = list(recovery["completed"])
        self._failed = copy.deepcopy(recovery["failed"])
        self._intent = copy.deepcopy(recovery.get("intent"))

    def _recover_saved_job(self, saved):
        """Verify one durable intent without inference or changing caption bytes."""
        state, recovery = copy.deepcopy(saved["state"]), copy.deepcopy(saved["recovery"])
        paths = recovery["paths"]
        completed = set(recovery["completed"])
        by_path = {path: index for index, path in enumerate(paths)}
        failed = {item.get("index", by_path.get(item["path"])): item for item in recovery["failed"]}
        reports = {item["index"]: item for item in state["report"]["items"] if "index" in item}

        def interrupted(index, code="caption_interrupted"):
            path = paths[index]
            message = "caption 已被外部修改，保留当前原文" if code == "caption_conflict" else "上次任务未完成此图片，可重试"
            failed[index] = {"path": path, "filename": Path(path).name, "index": index, "code": code, "error": message}
            reports[index] = {"filename": Path(path).name, "index": index,
                              "status": "error" if code == "caption_conflict" else "interrupted", "code": code, "error": message}

        intent = recovery.get("intent")
        if intent:
            index = intent["index"]
            if type(index) is not int or not 0 <= index < len(paths):
                raise CaptionPersistenceError("任务写入记录损坏，已阻止新任务，请检查任务数据库")
            target = caption_path_for(Path(paths[index]))
            with caption_file_lock(target):
                try:
                    recover_caption_write(self.job_store, target)
                    current_hash = caption_sha256(target)
                    if not target.is_symlink() and current_hash == intent["after_hash"]:
                        result = {**intent["result"], "index": index, "recovered_write": True}
                        # A later committed writer may own identical bytes. Its
                        # rollback ownership must survive repair of old history.
                        record = self.job_store.format_record(target)
                        may_claim = not record or record["after_hash"] != current_hash or record["writer_job_id"] == state["job_id"]
                        if result.get("caption_format") and may_claim:
                            self.job_store.remember_format(target, current_hash, result["caption_format"], result.get("tags", []), state["job_id"])
                        completed.add(index)
                        failed.pop(index, None)
                        reports[index] = result
                    else:
                        completed.discard(index)
                        before_hash = intent["result"].get("before_hash")
                        interrupted(index, "caption_interrupted" if not target.is_symlink() and current_hash == before_hash else "caption_conflict")
                except (sqlite3.Error, OSError):
                    raise CaptionPersistenceError("无法核验任务写入来源，已阻止新任务，请检查数据库后重试") from None
        for index, path in enumerate(paths):
            if index not in completed and index not in failed:
                interrupted(index)
        # Do not duplicate a success/report/count when the completion save
        # failed after in-memory bookkeeping already added the index.
        ordered_failed = [failed[index] for index in sorted(index for index in failed if index is not None)]
        ordered_reports = [reports[index] for index in sorted(reports)]
        state["report"] = {"items": ordered_reports}
        state["errors"] = [{"filename": item["filename"], "code": item["code"], "message": item["error"]} for item in ordered_failed]
        state.update(phase="error" if ordered_failed else "done", filename="",
                     message="已核验完成项，可重试未完成项" if ordered_failed else "已核验全部完成项",
                     succeeded=sum(bool(item.get("written")) for item in ordered_reports),
                     skipped=sum(item.get("status") == "skipped" for item in ordered_reports),
                     failed=len(ordered_failed), current=len(completed), recovered=True)
        # Preserve chronology so repairing old history cannot promote it over
        # the latest task during the next startup.
        state["recovered_at"] = time.time()
        recovery.update(completed=sorted(completed), failed=ordered_failed, intent=None)
        try:
            self.job_store.save(state, recovery["request"], paths, recovery["completed"], ordered_failed, None)
            if self.task_bridge:
                self.task_bridge.update(state, recovery["request"])
        except (sqlite3.Error, OSError, ValueError, KeyError):
            raise CaptionPersistenceError("无法保存任务恢复记录，已阻止新任务，请检查数据库后重试") from None
        return {"state": state, "recovery": recovery}

    def recover_pending(self):
        """Gate new jobs and rollback on successful recovery of all old writes."""
        with self._lock:
            if self.is_busy() or (self._thread and self._thread.is_alive()):
                raise RuntimeError("已有自然语言打标任务进行中")
            if self.job_store:
                self._recover()
            return self.status()

    def _persist_locked(self):
        if self.job_store and self._status.get("job_id") and self._request is not None:
            try:
                self.job_store.save(self._status, self._request, self._paths, self._completed, self._failed, self._intent)
            except (sqlite3.Error, OSError):
                raise CaptionPersistenceError("无法保存任务记录；请检查磁盘和数据库后重试") from None
        if self.task_bridge and self._status.get("job_id") and self._request:
            try:
                self.task_bridge.update(self._status, self._request)
            except (OSError, ValueError, KeyError):
                raise CaptionPersistenceError("无法保存任务档案；请检查user_data并重试") from None

    def detail(self, job_id):
        if self.status().get("job_id") == job_id:
            return self.status()
        saved = self.job_store.get(job_id) if self.job_store else None
        return saved["state"] if saved else None

    def history(self, limit=20):
        return self.job_store.history(limit) if self.job_store else ([self.status()] if self._status.get("job_id") else [])

    @staticmethod
    def _idle() -> dict:
        return {
            "job_id": None,
            "phase": "idle",
            "mode": None,
            "message": "",
            "current": 0,
            "total": 0,
            "filename": "",
            "succeeded": 0,
            "skipped": 0,
            "failed": 0,
            "cancelled": 0,
            "errors": [],
            "report": {"items": []},
            "updated_at": time.time(),
        }

    def status(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._status, ensure_ascii=False))

    def is_busy(self) -> bool:
        with self._lock:
            return self._status["phase"] in {"pending", "captioning", "cancelling"}

    def start(self, request: dict, *, retry_failed: bool = False, parent_job_id: str | None = None) -> dict:
        if request.get("mode", "natural") not in {"tag", "natural"}:
            raise RuntimeError("当前版本不支持组合打标；历史任务仅可查看或回滚")
        if request.get("mode", "natural") == "natural" and request.get("conflict_action", "ignore") not in {"ignore", "copy"}:
            raise RuntimeError("自然语言打标仅支持跳过或明确覆盖")
        with self._lock:
            if self.is_busy() or (self._thread and self._thread.is_alive()):
                raise RuntimeError("已有自然语言打标任务进行中")
            self.recover_pending()
            request = copy.deepcopy(request)
            if request.get("mode", "natural") == "natural":
                request.setdefault("conflict_action", "ignore")
                request.setdefault("concurrency", 3)
                if type(request["concurrency"]) is not int or not 1 <= request["concurrency"] <= 16:
                    raise RuntimeError("并发请求数必须是 1 到 16 的整数")
            elif "concurrency" in request:
                raise RuntimeError("Tag 打标不支持并发请求参数")
            paths = [Path(item) for item in request.get("paths", [])] or discover_images(request.get("path", ""), bool(request.get("recursive", False)))
            if "expected_hashes" not in request:
                request["expected_hashes"] = {}
                for path in paths:
                    target = caption_path_for(path)
                    with caption_file_lock(target):
                        if self.job_store:
                            recover_caption_write(self.job_store, target)
                        request["expected_hashes"][str(path)] = caption_sha256(target)
            job_service = self.service
            if self.service is None:
                from mikazuki.llm.runtime import llm_service
                job_service = llm_service
            from mikazuki.llm.service import UnifiedLLMService
            if isinstance(job_service, UnifiedLLMService) and request.get("mode") != "tag":
                manager = self

                class CaptionLLMService(UnifiedLLMService):
                    """Remote requests overlap; local/fallback inference stays serial."""

                    async def _request(self, profile, payload):
                        def check_cancelled():
                            if manager._cancel.is_set() or tagger_progress.is_cancel_requested():
                                raise CaptionJobCancelled()

                        async def send():
                            from mikazuki.llm.scheduler import local_request_slot
                            from mikazuki.llm import service as service_module
                            check_cancelled()
                            kwargs = {"session_factory": self.session_factory} if self.session_factory is not None else {}
                            async with local_request_slot(profile):
                                # Shared scheduler admission can await too.
                                check_cancelled()
                                return await service_module.chat_completion(profile, payload, **kwargs)

                        check_cancelled()
                        if profile.source == "remote":
                            return await send()
                        from mikazuki.llm.http import LLMRequestError
                        async with self.local_limit:
                            check_cancelled()
                            while True:
                                check_cancelled()
                                try:
                                    return await send()
                                except LLMRequestError as error:
                                    if error.code != "llm_local_queue_full":
                                        raise
                                    # Translation can already occupy all shared slots.
                                    # No inference started: wait for admission rather
                                    # than failing this image or adding another slot.
                                    await asyncio.sleep(.05)

                job_service = CaptionLLMService(
                    job_service.config_store,
                    session_factory=job_service.session_factory,
                    config_snapshot=job_service.config(masked=False),
                )
                job_service.local_limit = asyncio.Semaphore(1)
            from mikazuki.tagger.caption import snapshot_prompt
            if request.get("mode") != "tag":
                config = job_service.config(masked=False) if request.get("prompt_id") and not request.get("_prompt_frozen") and hasattr(job_service, "config") else {}
                request = snapshot_prompt(request, config)
                if hasattr(job_service, "resolve"):
                    from mikazuki.llm.config import config_revision
                    selected = job_service.resolve("vision", language=request["language"], profile_id=request.get("profile_id"), allow_local_fallback=bool(request.get("allow_local_fallback", False)))
                    request["model_snapshot"] = {"id": selected.id, "model": selected.model, "source": selected.source, "capabilities": list(selected.capabilities), "revision": config_revision(selected)}
            else:
                request.setdefault("interrogator_model", "wd14-convnextv2-v2")
                request["model_snapshot"] = {"id": request["interrogator_model"], "model": request["interrogator_model"], "source": "local", "capabilities": ["tag"]}
            if not tagger_progress.try_begin("captioning", str(request.get("interrogator_model") or ""), "自然语言打标任务已提交"):
                raise RuntimeError("已有打标或下载任务进行中")
            job_id = str(uuid.uuid4())
            self._cancel.clear()
            self._failed = []
            parent_job_id = (parent_job_id or self._status.get("job_id")) if retry_failed else None
            self._request = request
            self._request["path"] = str(Path(request.get("path", "")).expanduser().absolute())
            self._request["expected_hashes"] = {str(path.absolute()): request["expected_hashes"].get(str(path)) for path in paths}
            self._request["retry_failed"] = retry_failed
            self._job_service = job_service
            self._paths = [str(path.absolute()) for path in paths]
            self._completed = []
            self._intent = None
            self._status = {
                **self._idle(),
                "job_id": job_id,
                "phase": "pending",
                "mode": request.get("mode"),
                "message": "任务已提交",
                "total": len(paths),
                "parent_job_id": parent_job_id,
                "snapshot": {
                    "mode": request.get("mode") or "natural", "language": request.get("language") or "en",
                    "model_id": request.get("model_id") or request.get("interrogator_model"),
                    "runtime": request.get("runtime"), "profile_id": request.get("profile_id"),
                    "model_snapshot": request.get("model_snapshot"),
                    "max_tokens": request.get("max_tokens", 512), "temperature": request.get("temperature", 0.0),
                    "concurrency": request.get("concurrency", 3),
                    "conflict_action": request.get("conflict_action"), "recursive": bool(request.get("recursive", False)),
                    "prompt_id": request.get("prompt_id"),
                    "max_caption_length": request.get("max_caption_length", 2000),
                    "preset_revision": request.get("preset_revision"),
                    "template_revision": hashlib.sha256(str(request.get("prompt") or "").encode("utf-8")).hexdigest()[:24],
                    "allow_local_fallback": bool(request.get("allow_local_fallback", False)),
                },
            }
            if request.get("mode") == "tag":
                from .catalog import TAG_PARAMETERS, CAPTION_PARAMETERS
                for field in (*CAPTION_PARAMETERS, "preset_revision", "template_revision"):
                    self._status["snapshot"].pop(field, None)
                self._status["snapshot"].update({key: request[key] for key in TAG_PARAMETERS if key in request})
            self._thread = threading.Thread(target=self._run, args=(job_id,), daemon=True, name="caption-job")
            try:
                if self.task_bridge:
                    self._request["_task_archive"] = self.task_bridge.prepare(self._status, self._request, self._paths, lambda: self.cancel_task(job_id))
                self._persist_locked()
                self._thread.start()
            except Exception as exc:
                tagger_progress.release()
                self._status["phase"] = "error"
                self._status["message"] = "任务未启动，请检查任务档案和数据库存储"
                if self.task_bridge:
                    try:
                        self.task_bridge.update(self._status, self._request)
                    except (OSError, ValueError, KeyError):
                        self.task_bridge._project(self._status)
                if isinstance(exc, (OSError, ValueError)):
                    raise CaptionPersistenceError("无法保存任务档案，任务未启动") from None
                raise
            return self.status()

    def cancel(self) -> dict:
        with self._lock:
            if not self.is_busy():
                return self.status()
            self._cancel.set()
            tagger_progress.request_cancel()
            self._status["phase"] = "cancelling"
            self._status["message"] = "正在取消…"
            self._touch_locked()
            self._persist_locked()
            return self.status()

    def cancel_task(self, job_id: str) -> dict:
        with self._lock:
            if self._status.get("job_id") != job_id:
                return self.status()
            return self.cancel()

    def retry_failed(self, job_id: str | None = None) -> dict:
        with self._lock:
            if self.is_busy():
                raise RuntimeError("已有自然语言打标任务进行中")
            self.recover_pending()
            if job_id and job_id != self._status.get("job_id"):
                saved = self.job_store.get(job_id) if self.job_store else None
                if saved is None:
                    raise RuntimeError("任务不存在或已清理")
                request = dict(saved["recovery"]["request"])
                failed = saved["recovery"]["failed"]
            else:
                request = dict(self._request or {})
                failed = self._failed
                job_id = self._status.get("job_id")
            if not failed or not request:
                raise RuntimeError("没有可重试的失败项")
            request.pop("_task_archive", None)
            request["paths"] = [item["path"] for item in failed]
        return self.start(request, retry_failed=True, parent_job_id=job_id)

    def _touch_locked(self) -> None:
        self._status["updated_at"] = time.time()

    def _set(self, **values) -> None:
        with self._lock:
            self._status.update(values)
            if values.get("phase") in {"done", "error", "cancelled"}:
                self._status.setdefault("finished_at", time.time())
            self._touch_locked()
            self._persist_locked()

    def _run(self, job_id: str) -> None:
        request = dict(self._request or {})
        try:
            paths = [Path(item) for item in self._paths]
            self._set(phase="captioning", message="正在生成模型标签…" if request.get("mode") == "tag" else "正在生成自然语言描述…", total=len(paths))
            if not paths:
                self._set(phase="done", message="没有找到图片")
                return
            if str(request.get("mode") or "natural") == "tag":
                self._prepare_tag_model(request)
            asyncio.run(self._run_items(paths, request))
            if self._cancel.is_set():
                self._set(phase="cancelled", message="任务已取消", cancelled=len(paths) - len(self._completed), filename="")
            elif self._status["failed"] == len(paths):
                self._set(phase="error", message="任务失败，所有图片均未完成")
            elif self._status["failed"]:
                self._set(phase="done", message="任务完成，但存在失败项")
            else:
                self._set(phase="done", message="模型打标完成")
            if not self._cancel.is_set():
                self._set(current=len(paths), filename="")
        except (CaptionJobCancelled, TaggerCancelled):
            with self._lock:
                self._status.update(phase="cancelled", message="任务已取消", cancelled=max(self._status["total"] - self._status["current"], 0))
                self._status.setdefault("finished_at", time.time())
                self._touch_locked()
                try:
                    self._persist_locked()
                except CaptionPersistenceError:
                    pass
        except Exception as exc:
            message = safe_error_message(exc)
            with self._lock:
                self._status.update(phase="error", message=message, errors=[{"code": getattr(exc, "code", "caption_job_failed"), "message": message}])
                self._touch_locked()
                try:
                    self._persist_locked()
                except CaptionPersistenceError:
                    pass
        finally:
            terminal = self.status()
            if self.task_bridge:
                self.task_bridge._project(terminal)
            tagger_progress._touch(
                phase="done" if terminal["phase"] == "done" else "idle" if terminal["phase"] == "cancelled" else "error",
                message=terminal["message"],
            )
            tagger_progress.release()

    async def _run_items(self, paths: list[Path], request: dict) -> None:
        # A fixed worker pool bounds both active requests and memory. Each
        # worker keeps its own index; completion order may differ from discovery.
        pending = iter(enumerate(paths))

        async def worker():
            while not self._cancel.is_set():
                item = next(pending, None)
                if item is None:
                    return
                index, path = item
                try:
                    self._set(filename=path.name, message=f"正在处理 {path.name}")
                    await self._process_one(path, request, index)
                except (CaptionJobCancelled, TaggerCancelled):
                    self._cancel.set()
                    return
                except CaptionPersistenceError:
                    raise
                except Exception as exc:
                    # A persisted write intent must remain the sole pending
                    # transaction until recovery verifies it. Never let another
                    # image replace it after a storage/commit failure.
                    if isinstance(exc, sqlite3.Error) or self._intent is not None:
                        raise CaptionPersistenceError("无法保存图片写回记录；任务已停止，可重启后恢复") from exc
                    self._record_failure(index, path, exc)

        async def guarded_worker():
            try:
                await worker()
            except CaptionPersistenceError:
                # Stop every ready sibling immediately. gather's exception
                # propagation happens on a later loop turn, after another
                # worker could otherwise overwrite the recovery intent.
                self._cancel.set()
                raise

        count = 1 if request.get("mode") == "tag" else request.get("concurrency", 3)
        tasks = [asyncio.create_task(guarded_worker()) for _ in range(min(count, len(paths)))]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def _record_success(self, index: int, result: dict) -> dict:
        with self._lock:
            if not result["written"] and self._cancel.is_set():
                raise CaptionJobCancelled()
            result["index"] = index
            self._completed.append(index)
            self._completed.sort()
            intent = self._intent
            self._intent = None
            counter = "succeeded" if result["written"] else "skipped"
            items = sorted([*self._status["report"]["items"], result], key=lambda item: item["index"])
            try:
                self._set(report={"items": items}, current=len(self._completed),
                          **{counter: self._status[counter] + 1})
            except CaptionPersistenceError:
                self._intent = intent
                raise
            return result

    def _record_failure(self, index: int, path: Path, error: Exception) -> None:
        with self._lock:
            message = safe_error_message(error)
            code = getattr(error, "code", "caption_failed")
            self._failed.append({"path": str(path), "filename": path.name, "index": index, "error": message, "code": code})
            self._failed.sort(key=lambda item: item["index"])
            self._completed.append(index)
            self._completed.sort()
            items = sorted([*self._status["report"]["items"], {"filename": path.name, "index": index, "status": "error", "code": code, "error": message}], key=lambda item: item["index"])
            errors = [{"filename": item["filename"], "code": item["code"], "message": item["error"]} for item in self._failed]
            self._set(failed=len(self._failed), errors=errors, report={"items": items}, current=len(self._completed))

    async def _process_one(self, image_path: Path, request: dict, index: int) -> dict:
        from mikazuki.tagger.caption import default_caption_prompt, merge_tag_caption, parse_caption_response, render_prompt
        from mikazuki.llm.runtime import llm_service as runtime_llm_service
        from mikazuki.llm.config import config_revision
        from mikazuki.llm.service import UnifiedLLMService
        service = self._job_service or runtime_llm_service

        if self._cancel.is_set() or tagger_progress.is_cancel_requested():
            raise CaptionJobCancelled()

        mode = str(request.get("mode") or "natural")
        profile_id_for_report = None
        model_for_report = request.get("interrogator_model") if mode == "tag" else None
        source_for_report = "local" if mode == "tag" else None
        profile_revision_for_report = None
        prompt_revision_for_report = None
        cache_hit = False
        training_tags = []
        self._guard_path(image_path)
        image_hash = caption_sha256(image_path)
        target = caption_path_for(image_path)
        with caption_file_lock(target):
            if self.job_store:
                recover_caption_write(self.job_store, target)
            if target.is_symlink():
                raise CaptionWriteConflict("caption symlink cannot be overwritten")
            existing_bytes = target.read_bytes() if target.is_file() else None
            existing = existing_bytes.decode("utf-8", errors="replace") if existing_bytes is not None else ""
            before_hash = caption_sha256(target)
        expected = (
            request.get("expected_hashes", {}).get(str(image_path))
            if isinstance(request.get("expected_hashes"), dict)
            else caption_sha256(target)
        )
        action = str(request.get("conflict_action") or "copy")
        if before_hash != expected:
            raise CaptionWriteConflict("caption changed since the job snapshot")
        if action == "ignore" and target.exists():
            return self._record_success(index, {"filename": image_path.name, "status": "skipped", "written": False, "before_hash": before_hash, "after_hash": before_hash})
        if mode == "tag":
            training_tags = self._generate_tags(image_path, request)
            generated = ", ".join(training_tags)
        else:
            language = str(request.get("language") or "en")
            profile_id = request.get("profile_id") or None
            prompt_template = str(request.get("prompt") or default_caption_prompt(language))
            maximum = int(request.get("max_caption_length", 2000))
            prompt, _snapshot = render_prompt(prompt_template, language=language, mode=mode, image_name="image")
            system_prompt = str(request.get("system_prompt") or "")
            parameters_revision = json.dumps({"max_caption_length": maximum, "max_tokens": request.get("max_tokens", 512), "temperature": request.get("temperature", 0.0)}, sort_keys=True)
            prompt_revision = hashlib.sha256((prompt_template + chr(10) + system_prompt + chr(10) + _snapshot + chr(10) + parameters_revision).encode("utf-8")).hexdigest()[:24]
            preprocess_revision = "jpeg-white-matte-rgb-max1024-q85-v2"
            cache = self.cache
            if cache is None and self.service is None:
                from mikazuki.llm.runtime import caption_cache
                cache = caption_cache
            if not request.get("use_cache", True):
                cache = None
            if hasattr(service, "config") and not service.config(masked=False).get("cache", {}).get("caption", True):
                cache = None
            cache_generation = cache.generation() if cache is not None else None
            cached_profile = None

            def lookup_caption(candidate):
                """Consult each candidate only when remote-first reaches it.

                A local fallback result may be replayed after a remote outage,
                while a ready remote is still always tried first. Invalid old
                cache rows are ignored and naturally replaced by a provider
                result.
                """
                nonlocal cached_profile
                if cache is None:
                    return None
                value = cache.get(
                    image_hash or "",
                    config_revision(candidate),
                    prompt_revision,
                    language,
                    preprocess_revision,
                    expected_generation=cache_generation,
                )
                if not value:
                    return None
                try:
                    parse_caption_response(json.dumps({"caption": value, "language": language}), language=language, max_length=maximum)
                except Exception:
                    return None
                cached_profile = candidate
                return json.dumps({"caption": value, "language": language}, ensure_ascii=False)

            from mikazuki.llm.contracts import LLMContractError
            for attempt in range(2):
                try:
                    vision_options = {
                        "system_prompt": system_prompt,
                        "max_tokens": request.get("max_tokens", 512),
                        "temperature": request.get("temperature", 0.0),
                        "language": language,
                        "profile_id": profile_id,
                        "allow_local_fallback": bool(request.get("allow_local_fallback", False)),
                        "response_schema": {
                            "type": "object",
                            "properties": {"caption": {"type": "string", "minLength": 1, "maxLength": maximum}, "language": {"type": "string", "enum": [language]}},
                            "required": ["caption", "language"],
                            "additionalProperties": False,
                        },
                    }
                    # Third-party/fake service adapters may still implement
                    # the pre-cache complete_vision signature. The managed
                    # shared service is the only implementation that can
                    # safely inspect per-profile Caption cache keys.
                    if cache is not None and isinstance(service, UnifiedLLMService):
                        vision_options["candidate_cache"] = lookup_caption
                    _profile, _envelope, content, _image_info = await self._cancellable(service.complete_vision(
                        image_path,
                        prompt,
                        **vision_options,
                    ))
                    if _envelope.get("choices", [{}])[0].get("finish_reason") == "length":
                        raise LLMContractError("caption response was truncated")
                    result = parse_caption_response(content, language=language, max_length=maximum)
                    break
                except LLMContractError:
                    if attempt == 1:
                        raise
            generated = result.caption
            profile_id_for_report = _profile.id
            model_for_report = _profile.model
            source_for_report = _profile.source
            profile_revision_for_report = config_revision(_profile)
            cache_hit = cached_profile is not None and cached_profile.id == _profile.id
            if caption_sha256(image_path) != image_hash:
                raise CaptionWriteConflict("source image changed during caption generation")
            if cache is not None and not cache_hit:
                cache.put(
                    image_hash or "",
                    config_revision(_profile),
                    prompt_revision,
                    language,
                    preprocess_revision,
                    generated,
                    expected_generation=cache_generation,
                )
            prompt_revision_for_report = prompt_revision
        # No await occurs in this commit block: concurrent generation cannot
        # overlap backups, the single recovery intent, replacement or completion.
        # The lock also makes cancellation atomic with respect to a write.
        with self._lock, caption_file_lock(target):
            if self._cancel.is_set() or tagger_progress.is_cancel_requested():
                raise CaptionJobCancelled()
            if self.job_store:
                recover_caption_write(self.job_store, target)
            self._guard_path(image_path)
            if caption_sha256(image_path) != image_hash:
                raise CaptionWriteConflict("source image changed before caption write")
            current_target_hash = caption_sha256(target) if target.is_file() else None
            if current_target_hash != before_hash:
                raise CaptionWriteConflict("caption changed during caption generation")
            if mode == "tag":
                format_hint = self.job_store.find_format(target, before_hash) if self.job_store else None
                merged = merge_tag_caption(existing, generated, action, existed=target.is_file(), format_hint=format_hint)
            else:
                merged, _should_write = merge_caption(existing, generated, "copy" if action == "ignore" else action)
            output_format = "tag" if mode == "tag" else "natural"
            result = {
                "filename": image_path.name,
                "index": index,
                "image_sha256": image_hash,
                "caption_format": output_format,
                "tags": training_tags,
                "status": "written",
                "written": True,
                "before_hash": before_hash,
                "after_hash": hashlib.sha256((merged if mode == "tag" or merged.endswith("\n") else merged + "\n").encode("utf-8")).hexdigest(),
                "profile_id": profile_id_for_report,
                "model": model_for_report,
                "source": source_for_report,
                "profile_revision": profile_revision_for_report,
                "prompt_revision": prompt_revision_for_report,
                "cached": cache_hit,
            }
            if self.job_store:
                if existing_bytes is not None and hashlib.sha256(existing_bytes).hexdigest() != before_hash:
                    raise CaptionWriteConflict("caption changed before backup")
                from mikazuki.dataset_editor import detect_caption_format
                before_detail = self.job_store.find_format_detail(target, before_hash) or {"format": detect_caption_format(existing), "tags": []}
                before_detail["writer_job_id"] = self.job_store.format_owner(target, before_hash)
                self.job_store.backup(self._status["job_id"], index, existing_bytes, before_hash, before_detail)
                self._intent = {"index": index, "after_hash": result["after_hash"], "result": result}
                self._persist_locked()
            write_caption_atomic(target, merged, expected_sha256=expected, trailing_newline=mode != "tag")
            if self.job_store:
                self.job_store.remember_format(target, result["after_hash"], result["caption_format"], training_tags, self._status["job_id"])
            return self._record_success(index, result)

    async def _cancellable(self, operation):
        task = asyncio.create_task(operation)
        try:
            while not task.done():
                if self._cancel.is_set() or tagger_progress.is_cancel_requested():
                    self._cancel.set()
                    raise CaptionJobCancelled()
                await asyncio.wait({task}, timeout=0.05)
            if self._cancel.is_set():
                raise CaptionJobCancelled()
            return await task
        finally:
            if not task.done():
                task.cancel()
            # Admission may reject with CaptionJobCancelled before the polling
            # coroutine wakes. Retrieve even a finished task's exception.
            await asyncio.gather(task, return_exceptions=True)

    @staticmethod
    def _guard_path(image_path):
        from fastapi import HTTPException
        from mikazuki.datasets.inuse import ensure_path_not_in_use
        try:
            ensure_path_not_in_use(str(image_path))
        except HTTPException as error:
            if error.status_code == 409:
                raise CaptionDatasetInUse("训练任务正在使用此数据集，已阻止写回") from error
            raise

    @staticmethod
    def _prepare_tag_model(request: dict) -> None:
        from mikazuki.tagger.interrogator import available_interrogators
        from mikazuki.tagger.model_fetch import ensure_interrogator_assets, interrogator_assets_ready, use_download_endpoint

        model = str(request.get("interrogator_model") or "wd14-convnextv2-v2")
        interrogator = available_interrogators[model]
        if interrogator_assets_ready(interrogator, model):
            return
        with use_download_endpoint(str(request.get("download_endpoint") or "")):
            ensure_interrogator_assets(model, interrogator)

    @staticmethod
    def _generate_tags(image_path: Path, request: dict) -> list[str]:
        from PIL import Image
        from mikazuki.tagger.interrogator import available_interrogators
        from mikazuki.tagger.interrogators.base import Interrogator

        model = str(request.get("interrogator_model") or "wd14-convnextv2-v2")
        interrogator = available_interrogators[model]
        interrogator.load()
        try:
            with Image.open(image_path) as image:
                tags = interrogator.interrogate(image)
            return Interrogator.postprocess_tags(
                tags,
                float(request.get("threshold", 0.35)),
                float(request.get("character_threshold", 0.6)),
                bool(request.get("add_rating_tag", False)),
                bool(request.get("add_model_tag", False)),
                [item.strip() for item in str(request.get("additional_tags") or "").split(",") if item.strip()],
                [item.strip() for item in str(request.get("exclude_tags") or "").split(",") if item.strip()],
                False,
                False,
                bool(request.get("replace_underscore", True)),
                [item.strip() for item in str(request.get("replace_underscore_excludes") or "").split(",") if item.strip()],
                bool(request.get("escape_tag", True)),
            )
        finally:
            interrogator.unload()


caption_job_manager = CaptionJobManager()

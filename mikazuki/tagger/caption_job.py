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
from mikazuki.tagger.progress import tagger_progress

CaptionConflict = Literal["ignore", "copy", "prepend", "append"]
_UNSET_HASH = object()


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

    def __init__(self, service=None, cache=None, job_store=None):
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
        self._paths: list[str] = []
        self._completed: list[int] = []
        self._item_index = 0
        self._intent: dict | None = None
        if self.job_store:
            self._recover()

    def _recover(self):
        saved = self.job_store.get()
        if not saved:
            return
        self._status = saved["state"]
        recovery = saved["recovery"]
        self._request = recovery["request"]
        self._paths = recovery["paths"]
        self._completed = recovery["completed"]
        self._failed = recovery["failed"]
        self._intent = recovery.get("intent")
        if not self.is_busy() and (self._status["phase"] != "error" or len(self._completed) == len(self._paths)):
            return
        if self._intent:
            index = self._intent["index"]
            path = Path(self._paths[index])
            if index not in self._completed and caption_sha256(caption_path_for(path)) == self._intent["after_hash"]:
                self._completed.append(index)
                self._status["succeeded"] += 1
                self._status["report"]["items"].append({**self._intent["result"], "recovered_write": True})
                if self._intent["result"].get("caption_format"):
                    self.job_store.remember_format(caption_path_for(path), self._intent["after_hash"], self._intent["result"]["caption_format"])
        known = {item["path"] for item in self._failed}
        for index, path in enumerate(self._paths):
            if index not in self._completed and path not in known:
                item = {"path": path, "filename": Path(path).name, "code": "caption_interrupted", "error": "服务重启前未完成此图片，可重试"}
                self._failed.append(item)
                self._status["errors"].append({"filename": item["filename"], "code": item["code"], "message": item["error"]})
                self._status["report"]["items"].append({"filename": item["filename"], "index": index, "status": "interrupted", "error": item["error"]})
        self._intent = None
        self._status.update(phase="error" if self._failed else "done",
                            message="上次任务被服务重启中断；已保留完成项，可重试未完成项" if self._failed else "服务重启后已核验全部完成项", filename="",
                            failed=len(self._failed), current=len(self._completed), recovered=True)
        self._touch_locked()
        self._persist_locked()

    def _persist_locked(self):
        if self.job_store and self._status.get("job_id") and self._request is not None:
            try:
                self.job_store.save(self._status, self._request, self._paths, self._completed, self._failed, self._intent)
            except (sqlite3.Error, OSError):
                raise CaptionPersistenceError("无法保存任务记录；请检查磁盘和数据库后重试") from None

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

    def start(self, request: dict, *, retry_failed: bool = False) -> dict:
        with self._lock:
            if self.is_busy():
                raise RuntimeError("已有自然语言打标任务进行中")
            request = copy.deepcopy(request)
            paths = [Path(item) for item in request.get("paths", [])] or discover_images(request.get("path", ""), bool(request.get("recursive", False)))
            if "expected_hashes" not in request:
                request["expected_hashes"] = {str(path): caption_sha256(caption_path_for(path)) for path in paths}
            job_service = self.service
            if self.service is None:
                from mikazuki.llm.runtime import llm_service
                job_service = llm_service
            from mikazuki.llm.service import UnifiedLLMService
            if isinstance(job_service, UnifiedLLMService):
                job_service = UnifiedLLMService(
                    job_service.config_store,
                    session_factory=job_service.session_factory,
                    config_snapshot=job_service.config(masked=False),
                )
            from mikazuki.tagger.caption import snapshot_prompt
            if request.get("mode") != "tag":
                config = job_service.config(masked=False) if request.get("prompt_id") and not request.get("_prompt_frozen") and hasattr(job_service, "config") else {}
                request = snapshot_prompt(request, config)
            if not tagger_progress.try_begin("captioning", str(request.get("interrogator_model") or ""), "自然语言打标任务已提交"):
                raise RuntimeError("已有打标或下载任务进行中")
            job_id = str(uuid.uuid4())
            self._cancel.clear()
            self._failed = []
            parent_job_id = self._status.get("job_id") if retry_failed else None
            self._request = request
            self._request["retry_failed"] = retry_failed
            self._job_service = job_service
            self._paths = [str(path) for path in paths]
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
                    "mode": request.get("mode") or "natural", "language": request.get("language") or "zh-CN",
                    "prompt_id": request.get("prompt_id"),
                    "max_caption_length": request.get("max_caption_length", 2000),
                    "template_revision": hashlib.sha256(str(request.get("prompt") or "").encode("utf-8")).hexdigest()[:24],
                    "allow_local_fallback": bool(request.get("allow_local_fallback", False)),
                },
            }
            self._thread = threading.Thread(target=self._run, args=(job_id,), daemon=True, name="caption-job")
            try:
                self._persist_locked()
                self._thread.start()
            except Exception:
                tagger_progress.release()
                self._status["phase"] = "error"
                raise
            return self.status()

    def cancel(self) -> dict:
        with self._lock:
            if not self.is_busy():
                return self.status()
            self._cancel.set()
            self._status["phase"] = "cancelling"
            self._status["message"] = "正在取消…"
            self._touch_locked()
            self._persist_locked()
            return self.status()

    def retry_failed(self) -> dict:
        with self._lock:
            if self.is_busy():
                raise RuntimeError("已有自然语言打标任务进行中")
            if not self._failed or not self._request:
                raise RuntimeError("没有可重试的失败项")
            request = dict(self._request)
            request["paths"] = [item["path"] for item in self._failed]
        return self.start(request, retry_failed=True)

    def _touch_locked(self) -> None:
        self._status["updated_at"] = time.time()

    def _set(self, **values) -> None:
        with self._lock:
            self._status.update(values)
            self._touch_locked()
            self._persist_locked()

    def _run(self, job_id: str) -> None:
        request = dict(self._request or {})
        try:
            paths = [Path(item) for item in self._paths]
            self._set(phase="captioning", message="正在生成自然语言描述…", total=len(paths))
            if not paths:
                self._set(phase="done", message="没有找到图片")
                return
            if str(request.get("mode") or "natural") in {"tag", "combined"}:
                self._prepare_tag_model(request)
            for index, path in enumerate(paths, start=1):
                self._item_index = index - 1
                if self._cancel.is_set():
                    self._set(phase="cancelled", message="任务已取消", cancelled=len(paths) - index + 1)
                    return
                self._set(current=index - 1, filename=path.name, message=f"正在处理 {path.name}")
                try:
                    result = asyncio.run(self._process_one(path, request))
                    with self._lock:
                        result["index"] = index - 1
                        self._completed.append(index - 1)
                        self._intent = None
                        counter = "succeeded" if result["written"] else "skipped"
                        self._set(report={"items": [*self._status["report"]["items"], result]},
                                  current=index, **{counter: self._status[counter] + 1})
                except CaptionJobCancelled:
                    remaining = max(len(paths) - index + 1, 0)
                    self._set(
                        phase="cancelled",
                        message="任务已取消",
                        cancelled=self._status["cancelled"] + remaining,
                    )
                    return
                except Exception as exc:
                    message = safe_error_message(exc)
                    item = {"path": str(path), "filename": path.name, "error": message, "code": getattr(exc, "code", "caption_failed")}
                    self._failed.append(item)
                    self._completed.append(index - 1)
                    self._intent = None
                    self._set(
                        failed=self._status["failed"] + 1,
                        errors=[*self._status["errors"], {"filename": path.name, "code": getattr(exc, "code", "caption_failed"), "message": message}],
                        report={"items": [*self._status["report"]["items"], {"filename": path.name, "index": index - 1, "status": "error", "code": item["code"], "error": message}]},
                    )
            if self._cancel.is_set():
                self._set(phase="cancelled", message="任务已取消")
            elif self._status["failed"] == len(paths):
                self._set(phase="error", message="任务失败，所有图片均未完成")
            elif self._status["failed"]:
                self._set(phase="done", message="任务完成，但存在失败项")
            else:
                self._set(phase="done", message="自然语言打标完成")
            self._set(current=len(paths), filename="")
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
            tagger_progress._touch(
                phase="done" if terminal["phase"] == "done" else "idle" if terminal["phase"] == "cancelled" else "error",
                message=terminal["message"],
            )
            tagger_progress.release()

    async def _process_one(self, image_path: Path, request: dict) -> dict | bool:
        from mikazuki.tagger.caption import compose_caption, merge_tag_caption, parse_caption_response, render_prompt
        from mikazuki.llm.runtime import llm_service as runtime_llm_service
        from mikazuki.llm.config import config_revision
        service = self._job_service or runtime_llm_service

        mode = str(request.get("mode") or "natural")
        profile_id_for_report = None
        profile_revision_for_report = None
        prompt_revision_for_report = None
        cache_hit = False
        self._guard_path(image_path)
        image_hash = caption_sha256(image_path)
        target = caption_path_for(image_path)
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
        if action == "ignore" and target.exists():
            return {"filename": image_path.name, "status": "skipped", "written": False, "before_hash": before_hash, "after_hash": before_hash}
        if before_hash != expected:
            raise CaptionWriteConflict("caption changed since the job snapshot")
        if mode == "tag":
            generated = ", ".join(self._generate_tags(image_path, request))
        else:
            language = str(request.get("language") or "zh-CN")
            profile_id = request.get("profile_id") or None
            prompt_template = str(request.get("prompt") or '请用{{language}}（zh-CN 使用简体中文）描述图片中的主要可见内容，只返回 JSON 对象，字段必须为 caption 和 language；language 必须是 "{{language}}"，不要输出 Markdown。')
            maximum = int(request.get("max_caption_length", 2000))
            prompt, _snapshot = render_prompt(prompt_template, language=language, mode=mode, image_name="image")
            prompt_revision = hashlib.sha256((prompt_template + chr(10) + _snapshot + chr(10) + str(maximum)).encode("utf-8")).hexdigest()[:24]
            preprocess_revision = "jpeg-white-matte-rgb-max1024-q85-v2"
            cache = self.cache
            if cache is None and self.service is None:
                from mikazuki.llm.runtime import caption_cache
                cache = caption_cache
            if not request.get("use_cache", True):
                cache = None
            if hasattr(service, "config") and not service.config(masked=False).get("cache", {}).get("caption", True):
                cache = None
            cached = None
            if cache is not None:
                selected_profile = service.resolve("vision", language=language, profile_id=profile_id, allow_local_fallback=bool(request.get("allow_local_fallback", False)))
                cached = cache.get(
                    image_hash or "",
                    config_revision(selected_profile),
                    prompt_revision,
                    language,
                    preprocess_revision,
                )
            if cached:
                parse_caption_response(json.dumps({"caption": cached, "language": language}), language=language, max_length=maximum)
                generated = cached
                profile_id_for_report = selected_profile.id
                profile_revision_for_report = config_revision(selected_profile)
                cache_hit = True
            else:
                from mikazuki.llm.contracts import LLMContractError
                for attempt in range(2):
                    try:
                        _profile, _envelope, content, _image_info = await self._cancellable(service.complete_vision(
                            image_path,
                            prompt,
                            language=language,
                            profile_id=profile_id,
                            allow_local_fallback=bool(request.get("allow_local_fallback", False)),
                            response_schema={
                                "type": "object",
                                "properties": {"caption": {"type": "string", "minLength": 1, "maxLength": maximum}, "language": {"type": "string", "enum": [language]}},
                                "required": ["caption", "language"],
                                "additionalProperties": False,
                            },
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
                profile_revision_for_report = config_revision(_profile)
                if caption_sha256(image_path) != image_hash:
                    raise CaptionWriteConflict("source image changed during caption generation")
                if cache is not None:
                    cache.put(
                        image_hash or "",
                        config_revision(_profile),
                        prompt_revision,
                        language,
                        preprocess_revision,
                        generated,
                    )
            prompt_revision_for_report = prompt_revision
        if mode == "combined":
            tags = self._generate_tags(image_path, request)
            generated = compose_caption(tags, generated, str(request.get("layout") or "tags_then_caption"))
        if self._cancel.is_set():
            raise CaptionJobCancelled()
        self._guard_path(image_path)
        if caption_sha256(image_path) != image_hash:
            raise CaptionWriteConflict("source image changed before caption write")
        if mode == "tag":
            format_hint = self.job_store.find_format(target, before_hash) if self.job_store else None
            merged, should_write = merge_tag_caption(existing, generated, action, existed=target.is_file(), format_hint=format_hint), True
        else:
            merged, should_write = merge_caption(existing, generated, "copy" if action == "ignore" else action)
        if not should_write:
            return False
        from mikazuki.dataset_editor import detect_caption_format
        generated_format = "tag" if mode == "tag" else "natural" if mode == "natural" else "tag" if request.get("layout") == "tags_only" else "natural" if request.get("layout") == "caption_only" or not tags else "mixed"
        output_format = generated_format
        if mode != "tag" and action in {"prepend", "append"} and existing.strip():
            existing_format = self.job_store.find_format(target, before_hash) if self.job_store else None
            existing_format = existing_format or detect_caption_format(existing)
            if existing_format != generated_format or existing_format == "mixed":
                output_format = "mixed"
        result = {
            "filename": image_path.name,
            "index": self._item_index,
            "image_sha256": image_hash,
            "caption_format": output_format,
            "status": "written",
            "written": True,
            "before_hash": before_hash,
            "after_hash": hashlib.sha256((merged if mode == "tag" or merged.endswith("\n") else merged + "\n").encode("utf-8")).hexdigest(),
            "profile_id": profile_id_for_report,
            "profile_revision": profile_revision_for_report,
            "prompt_revision": prompt_revision_for_report,
            "cached": cache_hit,
        }
        if self.job_store:
            if existing_bytes is not None and hashlib.sha256(existing_bytes).hexdigest() != before_hash:
                raise CaptionWriteConflict("caption changed before backup")
            self.job_store.backup(self._status["job_id"], self._item_index, existing_bytes, before_hash)
            with self._lock:
                self._intent = {"index": self._item_index, "after_hash": result["after_hash"], "result": result}
                self._persist_locked()
        write_caption_atomic(target, merged, expected_sha256=expected, trailing_newline=mode != "tag")
        if self.job_store:
            self.job_store.remember_format(target, result["after_hash"], result["caption_format"])
        return result

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

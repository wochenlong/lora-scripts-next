from __future__ import annotations

import hashlib
import asyncio
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

CaptionConflict = Literal["ignore", "copy", "prepend", "append"]


class CaptionWriteConflict(RuntimeError):
    code = "caption_conflict"


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
        return generated + separator + existing.strip(), True
    if action == "append":
        return existing.strip() + separator + generated, True
    raise ValueError(f"unknown caption conflict action: {action}")


def write_caption_atomic(
    path: Path,
    caption: str,
    *,
    expected_sha256: str | None = None,
) -> str:
    current_sha256 = caption_sha256(path)
    if expected_sha256 is not None and current_sha256 != expected_sha256:
        raise CaptionWriteConflict("caption changed while the job was running")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as target:
            target.write(caption.strip())
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
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

    def __init__(self, service=None):
        self.service = service
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._request: dict | None = None
        self._status: dict = self._idle()
        self._failed: list[dict] = []

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
            "failed": 0,
            "cancelled": 0,
            "errors": [],
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
            job_id = str(uuid.uuid4())
            self._cancel.clear()
            self._failed = []
            self._request = dict(request)
            self._request["retry_failed"] = retry_failed
            self._status = {
                **self._idle(),
                "job_id": job_id,
                "phase": "pending",
                "mode": request.get("mode"),
                "message": "任务已提交",
            }
            self._thread = threading.Thread(target=self._run, args=(job_id,), daemon=True, name="caption-job")
            self._thread.start()
            return self.status()

    def cancel(self) -> dict:
        with self._lock:
            if not self.is_busy():
                return self.status()
            self._cancel.set()
            self._status["phase"] = "cancelling"
            self._status["message"] = "正在取消…"
            self._touch_locked()
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

    def _run(self, job_id: str) -> None:
        request = dict(self._request or {})
        try:
            paths = [Path(item) for item in request.get("paths", [])]
            if not paths:
                paths = discover_images(request.get("path", ""), bool(request.get("recursive", False)))
            self._set(phase="captioning", message="正在生成自然语言描述…", total=len(paths))
            if not paths:
                self._set(phase="done", message="没有找到图片")
                return
            if str(request.get("mode") or "natural") in {"tag", "combined"}:
                self._prepare_tag_model(request)
            for index, path in enumerate(paths, start=1):
                if self._cancel.is_set():
                    self._set(phase="cancelled", message="任务已取消")
                    return
                self._set(current=index - 1, filename=path.name, message=f"正在处理 {path.name}")
                try:
                    result = asyncio.run(self._process_one(path, request))
                    if result:
                        self._set(succeeded=self._status["succeeded"] + 1)
                except Exception as exc:
                    item = {"path": str(path), "filename": path.name, "error": str(exc)}
                    self._failed.append(item)
                    self._set(
                        failed=self._status["failed"] + 1,
                        errors=[*self._status["errors"], {"filename": path.name, "code": getattr(exc, "code", "caption_failed"), "message": str(exc)}],
                    )
            if self._cancel.is_set():
                self._set(phase="cancelled", message="任务已取消")
            elif self._status["failed"]:
                self._set(phase="done", message="任务完成，但存在失败项")
            else:
                self._set(phase="done", message="自然语言打标完成")
            self._set(current=len(paths), filename="")
        except Exception as exc:
            self._set(phase="error", message=str(exc), errors=[{"code": "caption_job_failed", "message": str(exc)}])

    async def _process_one(self, image_path: Path, request: dict) -> bool:
        from mikazuki.tagger.caption import compose_caption, parse_caption_response, render_prompt
        from mikazuki.llm.runtime import llm_service as runtime_llm_service
        service = self.service or runtime_llm_service

        mode = str(request.get("mode") or "natural")
        if mode == "tag":
            generated = ", ".join(self._generate_tags(image_path, request))
        else:
            language = str(request.get("language") or "zh-CN")
            profile_id = request.get("profile_id") or None
            prompt_template = str(request.get("prompt") or "请用{{language}}简洁描述图片内容，只返回 JSON。")
            prompt, _snapshot = render_prompt(prompt_template, language=language, mode=mode, image_name=image_path.name)
            _profile, _envelope, content, _image_info = await service.complete_vision(
                image_path,
                prompt,
                language=language,
                profile_id=profile_id,
                response_schema={
                    "type": "object",
                    "properties": {"caption": {"type": "string"}, "language": {"type": "string"}},
                    "required": ["caption", "language"],
                    "additionalProperties": False,
                },
            )
            result = parse_caption_response(content, language=language)
            generated = result.caption
        if mode == "combined":
            tags = self._generate_tags(image_path, request)
            generated = compose_caption(tags, generated, str(request.get("layout") or "tags_then_caption"))
        target = caption_path_for(image_path)
        existing = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        expected = request.get("expected_hashes", {}).get(str(image_path)) if isinstance(request.get("expected_hashes"), dict) else caption_sha256(target)
        action = str(request.get("conflict_action") or "copy")
        merged, should_write = merge_caption(existing, generated, action)
        if not should_write:
            return False
        write_caption_atomic(target, merged, expected_sha256=expected)
        return True

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

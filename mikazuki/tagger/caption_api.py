from __future__ import annotations

from pathlib import Path
from typing import Literal
import asyncio

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from mikazuki.llm.runtime import llm_service
from mikazuki.llm.config import config_revision
from mikazuki.tagger.caption import DEFAULT_CAPTION_PROMPT, compose_caption, parse_caption_response, render_prompt, snapshot_prompt
from mikazuki.tagger.caption_job import CaptionJobCancelled, caption_job_manager
from mikazuki.tagger.progress import TaggerCancelled, tagger_progress


router = APIRouter()


def _ensure_path_not_in_use(path: str) -> None:
    from mikazuki.datasets.inuse import ensure_path_not_in_use
    ensure_path_not_in_use(path)


class CaptionJobRequest(BaseModel):
    path: str
    mode: Literal["natural", "combined", "tag"] = "natural"
    recursive: bool = False
    allow_local_fallback: bool = False
    use_cache: bool = True
    profile_id: str | None = None
    prompt_id: str | None = Field(default=None, max_length=80)
    prompt: str = Field(default=DEFAULT_CAPTION_PROMPT, max_length=8000)
    max_caption_length: int = Field(default=2000, ge=1, le=2000)
    language: Literal["zh-CN", "zh-TW", "en", "ja"] = "zh-CN"
    layout: Literal["tags_then_caption", "caption_then_tags", "tags_only", "caption_only"] = "tags_then_caption"
    conflict_action: Literal["ignore", "copy", "prepend", "append"] = "copy"
    interrogator_model: str = "wd14-convnextv2-v2"
    download_endpoint: str = ""
    threshold: float = Field(default=0.35, ge=0, le=1)
    character_threshold: float = Field(default=0.6, ge=0, le=1)
    add_rating_tag: bool = False
    add_model_tag: bool = False
    additional_tags: str = ""
    exclude_tags: str = ""
    escape_tag: bool = True
    replace_underscore: bool = True
    replace_underscore_excludes: str = ""


class CaptionPreviewRequest(CaptionJobRequest):
    image_path: str


def _success(data=None, message=None):
    return {"status": "success", "message": message, "data": data}


def _snapshot_request(req):
    payload = req.dict()
    if req.prompt_id:
        for field in ("prompt", "language", "max_caption_length"):
            if field not in req.__fields_set__:
                payload.pop(field)
    config = llm_service.config(masked=False) if req.prompt_id else {}
    return snapshot_prompt(payload, config) if req.mode != "tag" else payload


@router.get("/tagger/jobs")
async def caption_job_status():
    return _success(caption_job_manager.status())


@router.post("/tagger/jobs")
async def start_caption_job(req: CaptionJobRequest):
    try:
        payload = _snapshot_request(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "caption_prompt_invalid", "message": "提示词预设或模板无效，请检查设置"}) from exc
    if req.mode != "tag":
        try:
            llm_service.resolve("vision", language=payload["language"], profile_id=req.profile_id, allow_local_fallback=req.allow_local_fallback)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"code": getattr(exc, "code", "llm_capability_vision_required"), "message": str(exc)}) from exc
    try:
        _ensure_path_not_in_use(req.path)
    except HTTPException:
        raise
    if not Path(req.path).expanduser().is_dir():
        raise HTTPException(status_code=400, detail="打标路径不是目录")
    try:
        data = caption_job_manager.start(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _success(data, "自然语言打标任务已提交")


@router.post("/tagger/jobs/cancel")
async def cancel_caption_job():
    if not caption_job_manager.is_busy() and tagger_progress.get()["phase"] in {"captioning", "cancelling"}:
        tagger_progress.request_cancel()
    return _success(caption_job_manager.cancel(), "取消请求已提交")


@router.post("/tagger/jobs/retry-failed")
async def retry_caption_job():
    try:
        return _success(caption_job_manager.retry_failed(), "失败项重试已提交")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/tagger/jobs/history")
async def caption_job_history(limit: int = Query(default=20, ge=1, le=100)):
    return _success({"jobs": caption_job_manager.history(limit)})


@router.get("/tagger/jobs/{job_id}")
async def caption_job_detail(job_id: str):
    status = caption_job_manager.detail(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="自然语言打标任务不存在")
    return _success(status)


@router.get("/tagger/jobs/{job_id}/report")
async def caption_job_report(job_id: str):
    status = caption_job_manager.detail(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="自然语言打标任务不存在")
    return _success({"job_id": job_id, "phase": status["phase"], "snapshot": status.get("snapshot", {}), "report": status["report"]})


@router.post("/tagger/jobs/{job_id}/cancel")
async def cancel_caption_job_detail(job_id: str):
    status = caption_job_manager.status()
    if status.get("job_id") != job_id:
        raise HTTPException(status_code=404, detail="自然语言打标任务不存在")
    return _success(caption_job_manager.cancel(), "取消请求已提交")


@router.post("/tagger/jobs/preview")
async def preview_caption(req: CaptionPreviewRequest, request: Request):
    image_path = Path(req.image_path).expanduser()
    if not image_path.is_file():
        raise HTTPException(status_code=400, detail="预览图片不存在")
    if req.mode == "tag":
        raise HTTPException(status_code=400, detail="Tag 模式预览请使用既有 Tagger")
    if not tagger_progress.try_begin("captioning", req.interrogator_model, "正在预览当前图片"):
        raise HTTPException(status_code=409, detail={"code": "tagger_busy", "message": "已有打标或下载任务进行中"})
    try:
        payload = _snapshot_request(req)
        language = payload["language"]
        profile = llm_service.resolve("vision", language=language, profile_id=req.profile_id, allow_local_fallback=req.allow_local_fallback)
        prompt, snapshot = render_prompt(payload["prompt"], language=language, mode=req.mode, image_name="image")
        _profile, envelope, content, image_info = await _preview_operation(llm_service.complete_vision(
            image_path,
            prompt,
            language=language,
            profile_id=profile.id,
            allow_local_fallback=req.allow_local_fallback,
            response_schema={"type": "object", "properties": {"caption": {"type": "string", "minLength": 1, "maxLength": payload["max_caption_length"]}, "language": {"type": "string", "enum": [language]}}, "required": ["caption", "language"], "additionalProperties": False},
        ), request)
        if envelope.get("choices", [{}])[0].get("finish_reason") == "length":
            from mikazuki.llm.contracts import LLMContractError
            raise LLMContractError("caption preview response was truncated")
        result = parse_caption_response(content, language=language, max_length=payload["max_caption_length"])
        tagger_progress.check_cancelled()
        tags = []
        if req.mode == "combined":
            await _preview_operation(asyncio.to_thread(caption_job_manager._prepare_tag_model, payload), request, blocking=True)
            tags = await _preview_operation(asyncio.to_thread(caption_job_manager._generate_tags, image_path, payload), request, blocking=True)
        tagger_progress.check_cancelled()
        caption = compose_caption(tags, result.caption, req.layout) if req.mode == "combined" else result.caption
    except (CaptionJobCancelled, TaggerCancelled):
        raise HTTPException(status_code=409, detail={"code": "caption_cancelled", "message": "预览已取消"}) from None
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"code": getattr(exc, "code", "caption_preview_failed"), "message": "预览失败，请检查图片、模型能力、语言和服务状态"}) from exc
    finally:
        tagger_progress._touch(phase="idle", message="预览已结束")
        tagger_progress.release()
    return _success({
        "caption": caption,
        "natural_caption": result.caption,
        "tags": tags,
        "language": result.language,
        "profile_id": _profile.id,
        "profile_revision": config_revision(_profile, prompt_revision=snapshot),
        "image": image_info,
        "finish_reason": envelope.get("choices", [{}])[0].get("finish_reason"),
    })


async def _preview_operation(operation, request, *, blocking=False):
    task = asyncio.create_task(operation)
    try:
        while not task.done():
            if tagger_progress.is_cancel_requested() or await request.is_disconnected():
                tagger_progress.request_cancel()
                raise CaptionJobCancelled()
            await asyncio.wait({task}, timeout=.05)
        return await task
    finally:
        if not task.done():
            if not blocking:
                task.cancel()
            # Native Tag inference cannot be killed safely. Keep the shared
            # reservation until it unloads; download sees the cancel flag.
            await asyncio.gather(task, return_exceptions=True)

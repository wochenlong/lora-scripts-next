from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mikazuki.llm.runtime import llm_service
from mikazuki.tagger.caption import parse_caption_response, render_prompt
from mikazuki.tagger.caption_job import caption_job_manager


router = APIRouter()


def _ensure_path_not_in_use(path: str) -> None:
    from mikazuki.datasets.inuse import ensure_path_not_in_use
    ensure_path_not_in_use(path)


class CaptionJobRequest(BaseModel):
    path: str
    mode: Literal["natural", "combined", "tag"] = "natural"
    recursive: bool = False
    profile_id: str | None = None
    prompt: str = Field(default="请用{{language}}简洁描述图片内容，只返回 JSON。", max_length=8000)
    language: str = "zh-CN"
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


@router.get("/tagger/jobs")
async def caption_job_status():
    return _success(caption_job_manager.status())


@router.post("/tagger/jobs")
async def start_caption_job(req: CaptionJobRequest):
    if req.mode != "tag":
        try:
            llm_service.resolve("vision", language=req.language, profile_id=req.profile_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"code": getattr(exc, "code", "llm_capability_vision_required"), "message": str(exc)}) from exc
    try:
        _ensure_path_not_in_use(req.path)
    except HTTPException:
        raise
    if not Path(req.path).expanduser().is_dir():
        raise HTTPException(status_code=400, detail="打标路径不是目录")
    try:
        data = caption_job_manager.start(req.dict())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _success(data, "自然语言打标任务已提交")


@router.post("/tagger/jobs/cancel")
async def cancel_caption_job():
    return _success(caption_job_manager.cancel(), "取消请求已提交")


@router.post("/tagger/jobs/retry-failed")
async def retry_caption_job():
    try:
        return _success(caption_job_manager.retry_failed(), "失败项重试已提交")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/tagger/jobs/{job_id}")
async def caption_job_detail(job_id: str):
    status = caption_job_manager.status()
    if status.get("job_id") != job_id:
        raise HTTPException(status_code=404, detail="自然语言打标任务不存在")
    return _success(status)


@router.post("/tagger/jobs/{job_id}/cancel")
async def cancel_caption_job_detail(job_id: str):
    status = caption_job_manager.status()
    if status.get("job_id") != job_id:
        raise HTTPException(status_code=404, detail="自然语言打标任务不存在")
    return _success(caption_job_manager.cancel(), "取消请求已提交")


@router.post("/tagger/jobs/preview")
async def preview_caption(req: CaptionPreviewRequest):
    image_path = Path(req.image_path).expanduser()
    if not image_path.is_file():
        raise HTTPException(status_code=400, detail="预览图片不存在")
    if req.mode == "tag":
        raise HTTPException(status_code=400, detail="Tag 模式预览请使用既有 Tagger")
    try:
        profile = llm_service.resolve("vision", language=req.language, profile_id=req.profile_id)
        prompt, snapshot = render_prompt(req.prompt, language=req.language, mode=req.mode, image_name=image_path.name)
        _profile, envelope, content, image_info = await llm_service.complete_vision(
            image_path,
            prompt,
            language=req.language,
            profile_id=profile.id,
            response_schema={"type": "object", "properties": {"caption": {"type": "string"}, "language": {"type": "string"}}, "required": ["caption", "language"], "additionalProperties": False},
        )
        result = parse_caption_response(content, language=req.language)
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"code": getattr(exc, "code", "caption_preview_failed"), "message": str(exc)}) from exc
    return _success({
        "caption": result.caption,
        "language": result.language,
        "profile_id": profile.id,
        "profile_revision": llm_service.revision(profile.id, prompt_revision=snapshot),
        "image": image_info,
        "finish_reason": envelope.get("choices", [{}])[0].get("finish_reason"),
    })

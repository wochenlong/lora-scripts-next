from __future__ import annotations

from pathlib import Path
from typing import Literal
import asyncio
import sqlite3

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, validator

from mikazuki.llm.runtime import llm_service
from mikazuki.llm.config import config_revision
from mikazuki.tagger.caption import parse_caption_response, render_prompt, snapshot_prompt
from mikazuki.tagger.caption_job import CaptionJobCancelled, caption_job_manager
from mikazuki.tagger.progress import TaggerCancelled, tagger_progress


router = APIRouter()


def _ensure_path_not_in_use(path: str) -> None:
    from mikazuki.datasets.inuse import ensure_path_not_in_use
    ensure_path_not_in_use(path)


class CaptionJobRequest(BaseModel):
    class Config:
        extra = "forbid"

    path: str
    model_id: str | None = Field(default=None, max_length=200)
    runtime: Literal["local", "api"] | None = None
    mode: Literal["natural", "tag"] = "natural"
    recursive: bool = False
    allow_local_fallback: bool = False
    use_cache: bool = True
    profile_id: str | None = None
    prompt_id: str | None = Field(default=None, max_length=80)
    # An omitted prompt is resolved after language validation so the backend
    # can choose a complete language-specific built-in template.
    prompt: str = Field(default="", max_length=8000)
    system_prompt: str = Field(default="", max_length=8000)
    max_caption_length: int = Field(default=2000, ge=1, le=2000)
    max_tokens: int = Field(default=512, ge=1, le=8192)
    temperature: float = Field(default=0.0, ge=0, le=2)
    language: Literal["zh-CN", "zh-TW", "en", "ja"] = "en"
    layout: Literal["tags_only", "caption_only"] = "caption_only"
    conflict_action: Literal["ignore", "copy", "prepend", "append"] = "ignore"
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

    @validator("mode", pre=True)
    def reject_combined(cls, value):
        if value == "combined":
            raise HTTPException(status_code=400, detail={"code": "caption_combined_unsupported", "message": "当前版本不支持组合打标，请选择 Tag 或自然语言 Caption"})
        return value

    @validator("layout", pre=True)
    def reject_combined_layout(cls, value):
        if value in {"tags_then_caption", "caption_then_tags"}:
            raise HTTPException(status_code=400, detail={"code": "tagger_parameter_unsupported", "message": "所选模型不支持组合布局"})
        return value


class CaptionPreviewRequest(CaptionJobRequest):
    image_path: str


def _success(data=None, message=None):
    return {"status": "success", "message": message, "data": data}


def _snapshot_request(req):
    from .catalog import TAG_PARAMETERS, CAPTION_PARAMETERS, validate_model_selection
    invalid = req.__fields_set__ & set(TAG_PARAMETERS if req.mode == "natural" else CAPTION_PARAMETERS)
    if invalid or (req.mode == "natural" and (req.conflict_action not in {"ignore", "copy"} or ("layout" in req.__fields_set__ and req.layout != "caption_only"))):
        raise HTTPException(status_code=400, detail={"code": "tagger_parameter_unsupported", "message": "所选模型不支持这些参数或输出操作"})
    payload = req.dict()
    for field in (TAG_PARAMETERS if req.mode == "natural" else CAPTION_PARAMETERS):
        payload.pop(field, None)
    payload.pop("layout", None)
    if req.mode == "natural":
        for field in ("prompt", "system_prompt"):
            if field not in req.__fields_set__:
                payload.pop(field, None)
    try:
        validate_model_selection(payload, llm_service.config(masked=False) if req.model_id and req.mode != "tag" else {})
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "tagger_model_capability_mismatch", "message": "模型、运行方式或输出能力不匹配"}) from None
    if req.prompt_id:
        for field in ("prompt", "language", "max_caption_length", "system_prompt"):
            if field not in req.__fields_set__:
                payload.pop(field, None)
    config = llm_service.config(masked=False) if req.prompt_id and req.mode != "tag" else {}
    if req.prompt_id:
        from mikazuki.llm.prompt_presets import list_presets
        config = {**config, "prompt_presets": [*config.get("prompt_presets", []), *list_presets()]}
        # Prefer the user_data version if a legacy preset has the same id.
        config["prompt_presets"] = list({item["id"]: item for item in config["prompt_presets"]}.values())
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
    report = status["report"]
    if caption_job_manager.job_store:
        for item in report["items"]:
            if isinstance(item.get("index"), int):
                item["rollback_status"] = caption_job_manager.job_store.rollback_status(job_id, item["index"])
    return _success({"job_id": job_id, "phase": status["phase"], "snapshot": status.get("snapshot", {}), "report": report})


@router.post("/tagger/jobs/{job_id}/rollback")
async def rollback_caption_job(job_id: str):
    from .caption_maintenance import rollback_job
    try:
        return _success(await asyncio.to_thread(rollback_job, caption_job_manager, job_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="自然语言打标任务不存在") from None
    except RuntimeError:
        raise HTTPException(status_code=409, detail="回滚不可用，请先结束任务并检查数据集占用状态") from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="无法保存回滚记录，请检查数据库并重试") from None


@router.delete("/tagger/jobs/{job_id}")
async def delete_caption_history(job_id: str):
    from .caption_maintenance import delete_history
    try:
        return _success(await asyncio.to_thread(delete_history, caption_job_manager, job_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="自然语言打标任务不存在") from None
    except RuntimeError:
        raise HTTPException(status_code=409, detail="请先结束任务再清理历史记录") from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="无法清理历史记录，请检查数据库并重试") from None


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
    try:
        payload = _snapshot_request(req)
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "caption_prompt_invalid", "message": "提示词预设或模板无效"}) from None
    if not tagger_progress.try_begin("captioning", req.interrogator_model, "正在预览当前图片"):
        raise HTTPException(status_code=409, detail={"code": "tagger_busy", "message": "已有打标或下载任务进行中"})
    try:
        if req.mode == "tag":
            def generate():
                caption_job_manager._prepare_tag_model(payload)
                tagger_progress.check_cancelled()
                return caption_job_manager._generate_tags(image_path, payload)

            tags = await _preview_operation(asyncio.to_thread(generate), request, blocking=True)
            tagger_progress.check_cancelled()
            return _success({"caption": ", ".join(tags), "tags": tags, "language": "native", "model_id": payload["interrogator_model"]})
        language = payload["language"]
        profile = llm_service.resolve("vision", language=language, profile_id=req.profile_id, allow_local_fallback=req.allow_local_fallback)
        prompt, snapshot = render_prompt(payload["prompt"], language=language, mode=req.mode, image_name="image")
        _profile, envelope, content, image_info = await _preview_operation(llm_service.complete_vision(
            image_path,
            prompt,
            system_prompt=payload.get("system_prompt", ""),
            max_tokens=payload["max_tokens"],
            temperature=payload["temperature"],
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
        caption = result.caption
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
        "tags": [],
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

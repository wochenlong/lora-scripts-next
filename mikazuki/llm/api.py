from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
import asyncio

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from .config import LLMContractError, validate_caption_translation_settings
from .contracts import LLMConfigConflict
from .runtime import llm_service, get_local_vision_service, caption_cache


router = APIRouter()


class CaptionTranslationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    profile_id: str | None = None
    allow_local_fallback: bool = False
    use_cache: bool = True

    class Config:
        extra = "forbid"


@router.post("/llm/caption-translation")
async def translate_caption_text(req: CaptionTranslationRequest, request: Request):
    from .caption_translation import CaptionTextTranslator
    from .contracts import LLMRouteError
    payload = req.dict()
    # The UI omits the fallback switch by design. Resolve that omission from
    # the shared configuration once at admission so the translator and its
    # cache/provider diagnostics use the same effective policy. Explicit API
    # false remains an opt-out.
    if "allow_local_fallback" not in req.__fields_set__:
        try:
            shared = llm_service.config(masked=False)
        except Exception:
            shared = {}
        payload["allow_local_fallback"] = bool(shared.get("local_fallback_enabled", True))
    operation = asyncio.create_task(CaptionTextTranslator(llm_service, caption_cache).translate(**payload))
    try:
        while not operation.done():
            if await request.is_disconnected():
                raise HTTPException(status_code=499, detail="译文请求已取消")
            await asyncio.wait({operation}, timeout=0.1)
        return _success(await operation)
    except HTTPException:
        raise
    except LLMRouteError as error:
        raise HTTPException(status_code=409, detail={"code": error.code, "message": "请在共享 LLM 配置中设置可用的中文文本翻译接口，或显式启用已启动的本地模型兜底"}) from None
    except Exception as error:
        raise HTTPException(status_code=502, detail={"code": getattr(error, "code", "llm_request_failed"), "message": "自然语言译文生成失败，请检查模型返回、接口配置或稍后重试"}) from None
    finally:
        if not operation.done():
            operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)


class LLMConnectionTestRequest(BaseModel):
    capability: Literal["text", "vision"] | None = None
    profile_id: str | None = None
    image_path: str | None = None
    prompt: str = Field(default='Reply with JSON: {"ok": true}.', max_length=8000)
    language: str | None = None


def _success(data: dict) -> dict:
    return {"status": "success", "message": None, "data": data}


def _configuration():
    try:
        return llm_service.config(masked=True)
    except LLMContractError:
        raise HTTPException(status_code=409, detail={"code": "llm_config_invalid", "message": "共享 LLM 配置无法读取，请检查或恢复配置"}) from None


@router.get("/llm/profiles")
async def list_llm_profiles():
    config = _configuration()
    profiles = config["profiles"]
    profiles.sort(key=lambda item: (0 if item.get("source") == "remote" else 1, str(item.get("name") or item.get("id"))))
    return _success(config)


@router.get("/tagger/models")
async def tagger_models():
    from mikazuki.tagger.catalog import model_catalog
    return _success({"models": model_catalog(_configuration(), get_local_vision_service().status())})


@router.get("/llm/config")
async def get_llm_config():
    return _success(_configuration())


@router.get("/llm/caption-translation/settings")
async def get_caption_translation_settings():
    config = _configuration()
    return _success({"settings": config["caption_translation"], "revision": config["revision"]})


@router.put("/llm/caption-translation/settings")
async def save_caption_translation_settings(payload: Any = Body(...)):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="自然语言翻译设置必须是对象")
    if set(payload) - {"revision", "settings"}:
        raise HTTPException(status_code=422, detail="自然语言翻译设置包含未知字段")
    if not isinstance(payload.get("revision"), str):
        raise HTTPException(status_code=409, detail={"code": "llm_config_conflict", "message": "请先读取共享配置，再带 revision 保存；当前草稿已保留"})
    try:
        settings = validate_caption_translation_settings(payload.get("settings"))
    except LLMContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    try:
        saved = llm_service.save_config({"revision": payload["revision"], "caption_translation": settings})
        from .caption_translation_gate import refresh_translation_gate
        refresh_translation_gate(llm_service)
        return _success({"settings": saved["caption_translation"], "revision": saved["revision"]})
    except LLMConfigConflict as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": "共享配置已改变，请刷新配置后重试；当前草稿已保留"}) from None
    except LLMContractError:
        raise HTTPException(status_code=409, detail={"code": "llm_config_invalid", "message": "共享 LLM 配置无法读取，请检查或恢复配置"}) from None
    except OSError:
        raise HTTPException(status_code=503, detail={"code": "caption_translation_storage_failed", "message": "无法保存自然语言翻译设置，请检查存储权限"}) from None


@router.get("/llm/local-vision/manifest")
async def local_vision_manifest():
    from .model_manifest import manifest
    return _success(manifest())


@router.put("/llm/config")
async def save_llm_config(payload: dict):
    try:
        if not isinstance(payload.get("revision"), str):
            raise LLMConfigConflict("请先读取共享配置，再带 revision 保存；当前草稿已保留")
        llm_service.save_config(payload)
        if "caption_translation" in payload:
            from .caption_translation_gate import refresh_translation_gate
            refresh_translation_gate(llm_service)
        return _success(llm_service.config(masked=True))
    except LLMConfigConflict as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": "共享配置已改变或缺少 revision，请刷新配置后重试；当前草稿已保留"}) from None
    except LLMContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/llm/prompt-presets")
async def list_prompt_presets():
    from .prompt_presets import document
    try:
        return _success(document())
    except LLMContractError as exc:
        raise HTTPException(status_code=409, detail={"code": "caption_preset_store_invalid", "message": str(exc)}) from exc
    except OSError:
        raise HTTPException(status_code=503, detail={"code": "caption_preset_storage_failed", "message": "无法读取提示词预设，请检查存储权限"}) from None


@router.put("/llm/prompt-presets")
async def save_prompt_presets(payload: dict):
    from .prompt_presets import save_document
    try:
        return _success(save_document(payload))
    except LLMContractError as exc:
        conflict = "revision conflict" in str(exc)
        message = "其他客户端已更新提示词预设，请刷新预设后重试；当前草稿已保留" if conflict else str(exc)
        raise HTTPException(status_code=409 if conflict else 400, detail={"code": "caption_preset_conflict" if conflict else "caption_preset_invalid", "message": message}) from exc
    except OSError:
        raise HTTPException(status_code=503, detail={"code": "caption_preset_storage_failed", "message": "无法保存提示词预设，请检查存储权限"}) from None


@router.post("/llm/prompt-presets/import-legacy")
async def import_legacy_prompt_presets(payload: dict):
    return await confirm_prompt_preset_import({**payload, "source": "legacy_config"})


def _preset_import_payload(payload):
    if payload.get("source") == "legacy_config":
        return {**payload, "presets": llm_service.config(masked=True).get("prompt_presets", [])}
    return payload


@router.post("/llm/prompt-presets/import-preview")
async def preview_prompt_preset_import(payload: dict):
    from .prompt_presets import preview_import
    try:
        return _success(preview_import(_preset_import_payload(payload)))
    except LLMContractError as exc:
        raise HTTPException(status_code=400, detail={"code": "caption_preset_import_invalid", "message": str(exc)}) from None
    except OSError:
        raise HTTPException(status_code=503, detail={"code": "caption_preset_storage_failed", "message": "无法预览预设导入"}) from None


@router.post("/llm/prompt-presets/import-confirmed")
async def confirm_prompt_preset_import(payload: dict):
    from .prompt_presets import commit_import
    if payload.get("confirmed") is not True:
        raise HTTPException(status_code=400, detail={"code": "caption_preset_confirmation_required", "message": "请先预览并确认导入提示词预设"})
    try:
        return _success(commit_import(_preset_import_payload(payload)))
    except LLMContractError as exc:
        raise HTTPException(status_code=409, detail={"code": "caption_preset_import_failed", "message": str(exc)}) from exc
    except OSError:
        raise HTTPException(status_code=503, detail={"code": "caption_preset_storage_failed", "message": "无法导入提示词预设，请检查存储权限"}) from None


@router.get("/llm/local-vision/status")
async def local_vision_status():
    return _success(get_local_vision_service().status())


@router.post("/llm/local-vision/setup")
async def setup_local_vision():
    return _success(get_local_vision_service().start_setup())


@router.post("/llm/local-vision/cancel")
async def cancel_local_vision_install():
    return _success(get_local_vision_service().cancel_download())


@router.post("/llm/local-vision/start")
async def start_local_vision():
    service = get_local_vision_service()
    if service._task and not service._task.done():
        raise HTTPException(status_code=409, detail="本地视觉模型仍在安装")
    try:
        return _success(await service.start_runtime())
    except Exception:
        raise HTTPException(status_code=409, detail="本地视觉模型尚未完整安装或启动失败，请查看安装状态")


@router.post("/llm/local-vision/stop")
async def stop_local_vision():
    from mikazuki.tagger.caption_job import caption_job_manager
    from mikazuki.tagger.progress import tagger_progress
    if caption_job_manager.is_busy() or (tagger_progress.is_busy() and tagger_progress.get()["phase"] in {"captioning", "cancelling"}):
        raise HTTPException(status_code=409, detail="请先取消打标任务再停止视觉服务")
    return _success(await get_local_vision_service().stop_runtime())


@router.post("/llm/connection-test")
async def llm_connection_test(req: LLMConnectionTestRequest):
    image_path = None
    if req.image_path:
        image_path = Path(req.image_path).expanduser()
        if not image_path.is_file():
            raise HTTPException(status_code=400, detail="测试图片不存在")
    try:
        result = await llm_service.connection_test(
            capability=req.capability,
            profile_id=req.profile_id,
            image_path=image_path,
            prompt=req.prompt,
            language=req.language,
        )
    except Exception as exc:
        code = getattr(exc, "code", "llm_connection_failed")
        # Provider exceptions can contain private image paths or response text.
        raise HTTPException(status_code=502, detail={"code": code, "message": "连接测试失败，请检查能力、语言、凭据和服务状态"}) from exc
    return _success(result)

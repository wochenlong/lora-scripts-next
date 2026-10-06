from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .config import LLMContractError
from .runtime import llm_service, get_local_vision_service


router = APIRouter()


class LLMConnectionTestRequest(BaseModel):
    capability: Literal["text", "vision"] = "text"
    profile_id: str | None = None
    image_path: str | None = None
    prompt: str = Field(default='Reply with JSON: {"ok": true}.', max_length=8000)
    language: str | None = None


def _success(data: dict) -> dict:
    return {"status": "success", "message": None, "data": data}


@router.get("/llm/profiles")
async def list_llm_profiles():
    config = llm_service.config(masked=True)
    profiles = config["profiles"]
    profiles.sort(key=lambda item: (0 if item.get("source") == "remote" else 1, str(item.get("name") or item.get("id"))))
    return _success(config)


@router.get("/llm/config")
async def get_llm_config():
    return _success(llm_service.config(masked=True))


@router.get("/llm/local-vision/manifest")
async def local_vision_manifest():
    from .local_vision import FILES, REVISION
    return _success({
        "id": "qwen3-vl-2b-local",
        "model": "Qwen3VL-2B-Instruct-Q4_K_M.gguf",
        "mmproj": "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf",
        "source": "Qwen/Qwen3-VL-2B-Instruct-GGUF",
        "revision": REVISION,
        "files": [{"name": name, "size_bytes": size, "sha256": sha} for name, size, sha in FILES],
        "capabilities": ["text", "vision"],
        "languages": ["zh-CN"],
        "estimated_download_bytes": 1552463168,
        "estimated_peak_rss_bytes": 3097571328,
        "runtime": "llama.cpp b11327",
        "notes": "CPU-only fallback candidate; remote profile remains preferred.",
    })


@router.put("/llm/config")
async def save_llm_config(payload: dict):
    try:
        llm_service.save_config(payload)
        return _success(llm_service.config_store.load_masked())
    except LLMContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    if caption_job_manager.is_busy():
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

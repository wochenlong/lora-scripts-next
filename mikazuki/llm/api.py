from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .config import LLMContractError
from .runtime import llm_service


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
    profiles = llm_service.profiles(masked=True)
    profiles.sort(key=lambda item: (0 if item.get("source") == "remote" else 1, str(item.get("name") or item.get("id"))))
    return _success({
        "version": llm_service.config(masked=True).get("version", 5),
        "profiles": profiles,
        "routes": llm_service.config(masked=True).get("routes", {}),
        "prompt_presets": llm_service.config(masked=True).get("prompt_presets", []),
    })


@router.get("/llm/config")
async def get_llm_config():
    return _success(llm_service.config(masked=True))


@router.put("/llm/config")
async def save_llm_config(payload: dict):
    try:
        llm_service.save_config(payload)
        return _success(llm_service.config_store.load_masked())
    except LLMContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
        raise HTTPException(status_code=502, detail={"code": code, "message": str(exc)}) from exc
    return _success(result)

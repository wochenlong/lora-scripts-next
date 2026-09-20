"""宿主网络设置；沿用插件宿主的同源、loopback 与运行令牌保护。"""
import json
import os
from pathlib import Path
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from .policy import config_path, load_settings, resolve_policy

router = APIRouter(prefix="/network", tags=["network"])


async def read_authority(request: Request):
    from mikazuki.plugin_marketplace.api import _require_read_authority
    return await _require_read_authority(request)


async def mutation_authority(request: Request):
    from mikazuki.plugin_marketplace.api import _require_mutation_authority
    return await _require_mutation_authority(request)


class Settings(BaseModel):
    mode: Literal["auto", "system", "manual", "direct"] = "auto"
    http_proxy: str = ""
    https_proxy: str = ""
    no_proxy: str = "localhost,127.0.0.1,::1"

    class Config:
        extra = "forbid"


def projection():
    saved = load_settings()
    policy = resolve_policy()
    from .policy import redact
    return {"status": "success", "data": {
        "settings": {key: redact(saved.get(key, default)) for key, default in Settings().dict().items()},
        "effective": policy.diagnostic(),
    }}


@router.get("/settings")
async def get_settings(_=Depends(read_authority)):
    return projection()


@router.put("/settings")
async def put_settings(settings: Settings, _=Depends(mutation_authority)):
    from urllib.parse import urlsplit
    data = settings.dict()
    for key in ("http_proxy", "https_proxy"):
        address = data[key]
        try:
            username = urlsplit(address if "://" in address else "http://" + address).username
        except ValueError:
            raise HTTPException(400, detail="无效的代理地址。") from None
        if username is not None:
            raise HTTPException(400, detail="界面不保存代理密码；认证代理请使用服务端环境变量。")
    if data["mode"] != "manual":
        data.pop("http_proxy")
        data.pop("https_proxy")
    try:
        resolve_policy(saved=data)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from None
    path = config_path().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return projection()

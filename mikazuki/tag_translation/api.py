"""FastAPI adapter for the migrated tag translation services."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

import aiohttp
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .runtime import dictionary_service, local_model_service, translation_manager, translation_store
from .providers import translate_mymemory
from .translation_service import normalize_locale


router = APIRouter()


def _success(data: dict) -> dict:
    return {"status": "success", "message": None, "data": data}


class TagTranslationRequest(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=500)
    locale: str = "zh-CN"
    provider: Literal["danbooru", "mymemory", "auto", "llm"] = "danbooru"
    local_only: bool = False
    refresh: bool = False


def _items(tags: list[str]) -> list[dict[str, object]]:
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for raw in tags:
        tag = str(raw or "").strip()
        if not tag or tag in seen or len(tag) > 200:
            continue
        seen.add(tag)
        result.append({"name": tag, "category": 0, "post_count": 0})
    return result


@router.get("/tag-translation/status")
async def tag_translation_status():
    return _success({"dictionary": dictionary_service.status(), "llm": translation_manager.status(), "local_model": local_model_service.status()})


@router.get("/tag-translation/dictionary/status")
async def tag_translation_dictionary_status():
    return _success(dictionary_service.status())


@router.post("/tag-translation/dictionary/check")
async def check_tag_translation_dictionary():
    return _success(await dictionary_service.check_update())


@router.post("/tag-translation/dictionary/update")
async def update_tag_translation_dictionary(force: bool = False):
    if not force:
        current = dictionary_service.status()
        if current.get("installed") and current.get("update_available") is not True:
            return _success(current)
    return _success(dictionary_service.start_update(force=force))


@router.post("/tag-translation/dictionary/retry")
async def retry_tag_translation_dictionary():
    return _success(dictionary_service.retry_update())


@router.post("/tag-translation/dictionary/cancel")
async def cancel_tag_translation_dictionary():
    return _success(dictionary_service.cancel_update())


@router.get("/tag-translation/local-model/status")
async def tag_translation_local_model_status():
    return _success(local_model_service.status())


@router.post("/tag-translation/local-model/install")
async def install_tag_translation_local_model(force: bool = False):
    return _success(local_model_service.start_download(force=force))


@router.post("/tag-translation/local-model/setup")
async def setup_tag_translation_local_model(force: bool = False):
    return _success(local_model_service.start_setup(force=force))


@router.post("/tag-translation/local-model/cancel")
async def cancel_tag_translation_local_model():
    return _success(local_model_service.cancel_download())


@router.post("/tag-translation/local-model/start")
async def start_tag_translation_local_model():
    try:
        local_status = local_model_service.status()
        if local_status.get("runtime_state") == "installing" or local_status.get("state") in {"downloading", "installing"}:
            raise HTTPException(status_code=409, detail="Local runtime setup is still in progress; wait for it to finish before starting the service")
        if not local_status.get("installed") or not local_status.get("runtime_installed"):
            raise HTTPException(status_code=409, detail="Install the managed local runtime before starting the service")
        return _success(await local_model_service.start_runtime())
    except HTTPException:
        raise
    except Exception as error:
        return _success(local_model_service.set_error(error))


@router.post("/tag-translation/local-model/stop")
async def stop_tag_translation_local_model():
    try:
        return _success(await local_model_service.stop_runtime())
    except Exception as error:
        return _success(local_model_service.set_error(error))


@router.post("/dataset/translate/v1/chat/completions")
async def proxy_local_tag_translation(request: Request):
    """Expose llama.cpp only through the main application API namespace."""
    status = local_model_service.status()
    if status["state"] != "running":
        return Response(
            content='{"error":{"message":"Local translation runtime is not running"}}',
            status_code=503,
            media_type="application/json",
        )
    body = await request.body()
    timeout = aiohttp.ClientTimeout(total=300)
    try:
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            async with session.post(
                local_model_service.upstream_endpoint(),
                data=body,
                headers={"Content-Type": request.headers.get("content-type", "application/json")},
            ) as upstream:
                response_body = await upstream.read()
                content_type = upstream.headers.get("content-type", "application/json")
                return Response(content=response_body, status_code=upstream.status, media_type=content_type.split(";")[0])
    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
        return Response(
            content=json.dumps({"error": {"message": str(error)}}),
            status_code=502,
            media_type="application/json",
        )


@router.get("/tag-translation/config")
async def tag_translation_config():
    return _success(translation_manager.get_config())


@router.put("/tag-translation/config")
async def save_tag_translation_config(payload: dict):
    if payload.get("llm_mode") == "local":
        local_status = local_model_service.status()
        from mikazuki.llm.config import UnifiedConfigStore
        from mikazuki.llm.service import UnifiedLLMService
        shared_profiles = UnifiedLLMService(UnifiedConfigStore(translation_manager.config_store.path)).profiles(masked=True)
        shared_text_ready = any(
            profile.get("source") != "remote" and profile.get("enabled") and profile.get("ready")
            and "text" in profile.get("capabilities", []) for profile in shared_profiles
        )
        if not shared_text_ready and (not local_status.get("installed") or local_status.get("state") != "running"):
            raise HTTPException(status_code=409, detail="Install and start the managed local runtime before enabling local LLM")
    # Selecting the remote route disables translation fallback, but leaves the
    # shared runtime available for captioning. Explicit stop owns its lifecycle.
    return _success(translation_manager.save_config(payload))


@router.get("/tag-translation/cache")
async def tag_translation_cache_status():
    return _success({
        "total": translation_store.result_count(),
        "mymemory": translation_store.result_count("mymemory"),
        "llm": translation_store.result_count("llm"),
    })


@router.delete("/tag-translation/cache")
async def clear_tag_translation_cache(provider: Literal["mymemory", "llm"] | None = None):
    translation_store.clear_results(provider)
    return _success({"provider": provider, "total": translation_store.result_count()})


@router.post("/tag-translation/resolve")
@router.post("/dataset-editor/tag-translations")
async def resolve_tag_translations(req: TagTranslationRequest):
    items = _items(req.tags)
    storage_locale = normalize_locale(req.locale)
    if not req.local_only:
        await dictionary_service.ensure(req.locale)
        await dictionary_service.wait_for_update()
    rows = dictionary_service.lookup([item["name"] for item in items])
    unresolved = [str(item["name"]) for item in items if str(item["name"]) not in rows]
    network: dict[str, str] = {}
    llm: dict[str, str] = {}
    network_cached: set[str] = set()
    llm_cached: set[str] = set()
    network_error: str | None = None
    llm_error: str | None = None
    mymemory_revision = "mymemory-v1"
    llm_revision = translation_manager.profile_revision()
    if not req.refresh:
        if not req.local_only and req.provider in {"mymemory", "auto"}:
            cached = translation_store.get_results(storage_locale, unresolved, "mymemory", mymemory_revision)
            network = {tag: str(row["text"]) for tag, row in cached.items() if row.get("text")}
            network_cached = set(network)
        if not req.local_only and req.provider in {"llm", "auto"}:
            cached = translation_store.get_results(storage_locale, unresolved, "llm", llm_revision)
            llm = {tag: str(row["text"]) for tag, row in cached.items() if row.get("text")}
            llm_cached = set(llm)
    if not req.local_only and req.provider in {"mymemory", "auto"}:
        missing = [tag for tag in unresolved if tag not in network]
        if missing:
            try:
                fetched = await translate_mymemory(missing, storage_locale)
                network.update(fetched)
                translation_store.save_results(storage_locale, "mymemory", mymemory_revision, items, fetched)
                if not fetched:
                    network_error = "network_no_result"
            except Exception as error:
                network_error = getattr(error, "code", "network_unavailable")
    if not req.local_only and req.provider in {"llm", "auto"}:
        missing = [item for item in items if str(item["name"]) in unresolved and str(item["name"]) not in network and str(item["name"]) not in llm]
        try:
            if missing:
                llm_rows = (
                    await translation_manager.resolve(storage_locale, missing, refresh=True)
                    if req.refresh
                    else await translation_manager.resolve(storage_locale, missing)
                )
            else:
                llm_rows = {}
        except Exception as error:
            llm_error = getattr(error, "code", "llm_request_failed")
            llm_rows = {}
        # TranslationManager returns metadata rows. The public API contract is
        # always tag -> string, even when the cache returns a full row object.
        llm.update({
            tag: str(row.get("text")) if isinstance(row, dict) else str(row)
            for tag, row in llm_rows.items()
            if (row.get("text") if isinstance(row, dict) else row)
        })
    result = []
    for item in items:
        tag = str(item["name"])
        row = rows.get(tag)
        text = row.get("text") if row else network.get(tag) or llm.get(tag)
        source = "danbooru" if row else ("mymemory" if tag in network else ("llm" if tag in llm else None))
        error_code = None
        if not text and not req.local_only and req.provider in {"mymemory", "auto", "llm"}:
            error_code = llm_error if tag in unresolved and llm_error else (
                network_error if tag in unresolved and network_error else "translation_missing"
            )
        result.append({
            "tag": tag,
            "translation": text,
            "source": source,
            "status": "hit" if text else ("error" if error_code and error_code != "translation_missing" else "missing"),
            "cached": tag in network_cached or tag in llm_cached,
            "error_code": error_code,
            "category": row.get("category") if row else None,
            "post_count": row.get("post_count") if row else None,
        })
    return _success({"items": result, "provider": req.provider, "locale": req.locale})

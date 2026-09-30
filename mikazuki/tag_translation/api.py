"""FastAPI adapter for the migrated tag translation services."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .runtime import dictionary_service, translation_manager, translation_store
from .providers import translate_mymemory


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
    return _success({"dictionary": dictionary_service.status(), "llm": translation_manager.status()})


@router.get("/tag-translation/config")
async def tag_translation_config():
    return _success(translation_manager.get_config())


@router.put("/tag-translation/config")
async def save_tag_translation_config(payload: dict):
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
    if not req.local_only:
        await dictionary_service.ensure(req.locale)
        await dictionary_service.wait_for_update()
    rows = dictionary_service.lookup([item["name"] for item in items])
    unresolved = [str(item["name"]) for item in items if str(item["name"]) not in rows]
    network: dict[str, str] = {}
    llm: dict[str, str] = {}
    network_cached: set[str] = set()
    llm_cached: set[str] = set()
    mymemory_revision = "mymemory-v1"
    llm_revision = translation_manager.profile_revision()
    if not req.refresh:
        if req.provider in {"mymemory", "auto"}:
            cached = translation_store.get_results(req.locale, unresolved, "mymemory", mymemory_revision)
            network = {tag: str(row["text"]) for tag, row in cached.items() if row.get("text")}
            network_cached = set(network)
        if req.provider in {"llm", "auto"}:
            cached = translation_store.get_results(req.locale, unresolved, "llm", llm_revision)
            llm = {tag: str(row["text"]) for tag, row in cached.items() if row.get("text")}
            llm_cached = set(llm)
    if not req.local_only and req.provider in {"mymemory", "auto"}:
        missing = [tag for tag in unresolved if tag not in network]
        if missing:
            fetched = await translate_mymemory(missing, req.locale)
            network.update(fetched)
            translation_store.save_results(req.locale, "mymemory", mymemory_revision, items, fetched)
    if not req.local_only and req.provider in {"llm", "auto"}:
        missing = [item for item in items if str(item["name"]) in unresolved and str(item["name"]) not in network and str(item["name"]) not in llm]
        llm_rows = await translation_manager.resolve(req.locale, missing) if missing else {}
        # TranslationManager returns metadata rows. The public API contract is
        # always tag -> string, even when the cache returns a full row object.
        llm = {
            tag: str(row.get("text")) if isinstance(row, dict) else str(row)
            for tag, row in llm_rows.items()
            if (row.get("text") if isinstance(row, dict) else row)
        }
    result = []
    for item in items:
        tag = str(item["name"])
        row = rows.get(tag)
        text = row.get("text") if row else network.get(tag) or llm.get(tag)
        source = "danbooru" if row else ("mymemory" if tag in network else ("llm" if tag in llm else None))
        result.append({
            "tag": tag,
            "translation": text,
            "source": source,
            "status": "hit" if text else "missing",
            "cached": tag in network_cached or tag in llm_cached,
            "error_code": None,
            "category": row.get("category") if row else None,
            "post_count": row.get("post_count") if row else None,
        })
    return _success({"items": result, "provider": req.provider, "locale": req.locale})

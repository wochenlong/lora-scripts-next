"""FastAPI adapter for the migrated tag translation services."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .runtime import dictionary_service, translation_manager
from .providers import translate_mymemory


router = APIRouter()


def _success(data: dict) -> dict:
    return {"status": "success", "message": None, "data": data}


class TagTranslationRequest(BaseModel):
    tags: list[str] = Field(default_factory=list, max_items=500)
    locale: str = "zh-CN"
    provider: Literal["danbooru", "mymemory", "auto", "llm"] = "danbooru"


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


@router.post("/tag-translation/resolve")
async def resolve_tag_translations(req: TagTranslationRequest):
    items = _items(req.tags)
    await dictionary_service.ensure(req.locale)
    await dictionary_service.wait_for_update()
    rows = dictionary_service.lookup([item["name"] for item in items])
    unresolved = [str(item["name"]) for item in items if str(item["name"]) not in rows]
    network = await translate_mymemory(unresolved, req.locale) if req.provider in {"mymemory", "auto"} else {}
    llm = await translation_manager.resolve(req.locale, [item for item in items if str(item["name"]) in unresolved and str(item["name"]) not in network]) if req.provider in {"llm", "auto"} else {}
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
            "category": row.get("category") if row else None,
            "post_count": row.get("post_count") if row else None,
        })
    return _success({"items": result, "provider": req.provider, "locale": req.locale})

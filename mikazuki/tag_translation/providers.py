"""Small network provider adapter used by the migrated translation service."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


MYMEMORY_URL = "https://api.mymemory.translated.net/get"


def _acceptable(text: Any, tag: str, locale: str) -> bool:
    value = str(text or "").strip()
    if not value or value.casefold() == tag.casefold() or any(c in value for c in "\r\n\x00"):
        return False
    if str(locale).lower().startswith("zh"):
        return any("\u3400" <= c <= "\u9fff" for c in value)
    return True


async def _translate_one(session: aiohttp.ClientSession, tag: str, locale: str) -> str | None:
    async with session.get(
        MYMEMORY_URL,
        params={"q": tag, "langpair": f"en|{locale}"},
        headers={"Accept": "application/json", "User-Agent": "Next-Trainer-Tag-Translation"},
    ) as response:
        if response.status != 200:
            return None
        payload = await response.json(content_type=None)
    if not isinstance(payload, dict) or payload.get("quotaFinished") is True or payload.get("responseStatus") not in {None, 200}:
        return None
    response_data = payload.get("responseData")
    value = response_data.get("translatedText") if isinstance(response_data, dict) else None
    return str(value).strip() if _acceptable(value, tag, locale) else None


async def translate_mymemory(tags: list[str], locale: str = "zh-CN", *, timeout_seconds: float = 15.0) -> dict[str, str]:
    if not tags or not str(locale).lower().startswith("zh"):
        return {}
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    semaphore = asyncio.Semaphore(4)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async def run(tag: str) -> tuple[str, str | None]:
            async with semaphore:
                try:
                    return tag, await _translate_one(session, tag, "zh-CN")
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    return tag, None

        pairs = await asyncio.gather(*(run(tag) for tag in dict.fromkeys(tags)))
    return {tag: value for tag, value in pairs if value}

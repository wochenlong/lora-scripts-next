from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any

import aiohttp

from .client import extract_chat_content
from .contracts import LLMContractError, LLMProfile


class LLMRequestError(RuntimeError):
    def __init__(self, message: str, code: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


async def chat_completion(
    profile: LLMProfile,
    payload: Mapping[str, Any],
    *,
    session_factory: Callable[..., Any] = aiohttp.ClientSession,
    timeout_seconds: float = 180,
    retries: int = 1,
) -> tuple[dict[str, Any], str]:
    if not profile.endpoint:
        raise LLMRequestError("profile endpoint is empty", "llm_not_configured")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if profile.api_key:
        headers["Authorization"] = f"Bearer {profile.api_key}"
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    last_error: Exception | None = None
    for attempt in range(max(0, retries) + 1):
        try:
            async with session_factory(timeout=timeout, trust_env=True) as session:
                async with session.post(profile.endpoint, json=dict(payload), headers=headers) as response:
                    text = await response.text()
                    if response.status == 401 or response.status == 403:
                        raise LLMRequestError("LLM rejected the configured credentials", "llm_auth_failed")
                    if response.status == 429 or response.status >= 500:
                        raise LLMRequestError(
                            f"LLM returned retryable HTTP {response.status}",
                            "llm_request_failed",
                            retryable=True,
                        )
                    if response.status != 200:
                        raise LLMRequestError(
                            f"LLM returned HTTP {response.status}",
                            "llm_request_failed",
                        )
                    try:
                        envelope = await response.json(content_type=None)
                    except (ValueError, aiohttp.ContentTypeError) as exc:
                        raise LLMContractError("LLM response is not valid JSON") from exc
                    if not isinstance(envelope, dict):
                        raise LLMContractError("LLM response envelope must be an object")
                    return envelope, extract_chat_content(envelope)
        except LLMRequestError as exc:
            last_error = exc
            if not exc.retryable or attempt >= retries:
                raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_error = exc
            if attempt >= retries:
                raise LLMRequestError("LLM endpoint is unreachable", "llm_unreachable", retryable=True) from exc
        await asyncio.sleep(min(2 ** attempt, 8))
    raise LLMRequestError(str(last_error or "LLM request failed"), "llm_request_failed", retryable=True)

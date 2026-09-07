"""HTTP backend client for the Next Trainer API.

Every MCP tool funnels through BackendClient.request(), which unwraps the
APIResponse envelope and converts failures into BackendError so tools can
surface a clean message instead of a traceback.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx

DEFAULT_TIMEOUT = 10.0


class BackendError(Exception):
    """A backend call failed (connection, HTTP status, or APIResponse fail)."""


class BackendClient:
    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json_body: Any = None,
    ) -> dict:
        """Call the API and unwrap the APIResponse envelope.

        Returns the success payload: the ``data`` field when present, else the
        whole envelope. Raises BackendError on any failure.
        """
        try:
            resp = self._client.request(
                method,
                path,
                params={k: v for k, v in (params or {}).items() if v is not None},
                content=(
                    json.dumps(json_body).encode("utf-8")
                    if json_body is not None
                    else None
                ),
                headers=(
                    {"Content-Type": "application/json"}
                    if json_body is not None
                    else None
                ),
            )
        except httpx.ConnectError:
            raise BackendError(
                f"无法连接 Next Trainer 后端 {self.base_url} —— 请先启动 Next Trainer 主程序"
            )
        except httpx.HTTPError as exc:
            raise BackendError(f"请求后端失败: {exc}")

        try:
            payload = resp.json()
        except ValueError:
            raise BackendError(
                f"后端返回非 JSON (HTTP {resp.status_code}): {resp.text[:500]}"
            )

        if resp.status_code >= 400:
            detail = payload.get("detail") if isinstance(payload, dict) else None
            raise BackendError(
                f"后端 HTTP {resp.status_code}: {detail or resp.text[:500]}"
            )

        if isinstance(payload, dict) and payload.get("status") == "fail":
            raise BackendError(payload.get("message") or "后端返回失败")

        if isinstance(payload, dict) and "data" in payload:
            return payload["data"] if payload["data"] is not None else payload
        return payload if isinstance(payload, dict) else {"result": payload}

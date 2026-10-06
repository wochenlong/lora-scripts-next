import os

import httpx
from fastapi import APIRouter, Request
from httpx import ConnectError
from starlette.background import BackgroundTask
from starlette.responses import PlainTextResponse, StreamingResponse

router = APIRouter()


def reverse_proxy_maker(url_type: str, full_path: bool = False):
    if url_type == "tensorboard":
        host = os.environ.get("MIKAZUKI_TENSORBOARD_HOST", "127.0.0.1")
        port = os.environ.get("MIKAZUKI_TENSORBOARD_PORT", "6006")
    else:
        raise ValueError(f"unsupported proxy type: {url_type}")

    # httpx 0.28 removed the legacy ``proxies`` keyword. ``trust_env=False``
    # keeps this local reverse proxy independent from shell proxy variables.
    client = httpx.AsyncClient(base_url=f"http://{host}:{port}/", trust_env=False, timeout=360)

    async def _reverse_proxy(request: Request):
        if full_path:
            url = httpx.URL(path=request.url.path, query=request.url.query.encode("utf-8"))
        else:
            url = httpx.URL(
                path=request.path_params.get("path", ""),
                query=request.url.query.encode("utf-8")
            )
        rp_req = client.build_request(
            request.method, url,
            headers=request.headers.raw,
            content=request.stream() if request.method != "GET" else None
        )
        try:
            rp_resp = await client.send(rp_req, stream=True)
        except ConnectError:
            hint = (
                "The requested service not started yet or service started fail. "
                "This may cost a while when you first time startup.\n"
                "请求的服务尚未启动或启动失败。若是第一次启动，可能需要等待一段时间后再刷新网页。"
            )
            return PlainTextResponse(content=hint, status_code=502)
        return StreamingResponse(
            rp_resp.aiter_raw(),
            status_code=rp_resp.status_code,
            headers=rp_resp.headers,
            background=BackgroundTask(rp_resp.aclose),
        )

    return _reverse_proxy


router.add_route("/proxy/tensorboard/{path:path}", reverse_proxy_maker("tensorboard"), ["GET", "POST"])
router.add_route("/font-roboto/{path:path}", reverse_proxy_maker("tensorboard", full_path=True), ["GET", "POST"])

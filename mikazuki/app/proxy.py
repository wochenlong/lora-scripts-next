import os
import re
import json

import httpx
from fastapi import APIRouter, Request
from starlette.background import BackgroundTask
from starlette.responses import PlainTextResponse, RedirectResponse, Response, StreamingResponse

router = APIRouter()


def reverse_proxy_maker(url_type: str, full_path: bool = False):
    if url_type not in {"tensorboard", "monitor"}:
        raise ValueError(f"unsupported proxy type: {url_type}")

    async def _reverse_proxy(request: Request):
        prefix = "MIKAZUKI_TENSORBOARD" if url_type == "tensorboard" else "TRAIN_MONITOR"
        # Fail closed before constructing a client: an occupied disabled port
        # may belong to an unrelated process, including one accepting writes.
        if os.environ.get(f"{prefix}_ENABLED") != "1":
            return PlainTextResponse(f"{url_type} is disabled.", status_code=503)
        host = os.environ.get(f"{prefix}_HOST", "127.0.0.1") if url_type == "tensorboard" else "127.0.0.1"
        host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = os.environ.get(f"{prefix}_PORT", "6007" if url_type == "tensorboard" else "6008")
        client = httpx.AsyncClient(base_url=f"http://{host}:{port}/", trust_env=False, timeout=360)
        if full_path:
            url = httpx.URL(path=request.url.path, query=request.url.query.encode("utf-8"))
        else:
            url = httpx.URL(
                path="/" + request.path_params.get("path", "").lstrip("/"),
                query=request.url.query.encode("utf-8")
            )
        rp_req = client.build_request(
            request.method, url,
            headers=[(key, value) for key, value in request.headers.raw
                     if key.lower() not in {b"host", b"connection", b"transfer-encoding"}],
            content=request.stream() if request.method != "GET" else None
        )
        try:
            rp_resp = await client.send(rp_req, stream=True)
        except httpx.RequestError:
            await client.aclose()
            hint = (
                "The requested service not started yet or service started fail. "
                "This may cost a while when you first time startup.\n"
                "请求的服务尚未启动或启动失败。若是第一次启动，可能需要等待一段时间后再刷新网页。"
            )
            return PlainTextResponse(content=hint, status_code=502)

        async def close_upstream():
            try:
                await rp_resp.aclose()
            finally:
                await client.aclose()

        if url_type == "monitor":
            try:
                content = await rp_resp.aread()
                content_type = rp_resp.headers.get("content-type", "")
                if "application/json" in content_type:
                    payload = json.loads(content)
                    if isinstance(payload, dict):
                        for preview in payload.get("previews", []):
                            if isinstance(preview, dict):
                                url = preview.get("url")
                                if isinstance(url, str) and url.startswith("/preview-image?"):
                                    preview["url"] = "/train-monitor" + url
                    content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                elif any(kind in content_type for kind in ("text/html", "javascript")):
                    # The standalone monitor uses a small, known set of
                    # root-relative resources; keep them under the GUI origin.
                    content = re.sub(
                        rb"""(["'])(/(?:static/|assets/logo\.png|favicon\.ico|api/status|preview-image))""",
                        rb"\1/train-monitor\2", content,
                    )
                headers = {key: value for key, value in rp_resp.headers.items()
                           if key.lower() not in {"content-length", "content-encoding", "transfer-encoding", "connection"}}
                return Response(content, status_code=rp_resp.status_code, headers=headers)
            finally:
                await close_upstream()
        return StreamingResponse(
            rp_resp.aiter_raw(),
            status_code=rp_resp.status_code,
            headers=rp_resp.headers,
            background=BackgroundTask(close_upstream),
        )

    return _reverse_proxy


router.add_route("/proxy/tensorboard/{path:path}", reverse_proxy_maker("tensorboard"), ["GET", "POST"])
router.add_route("/font-roboto/{path:path}", reverse_proxy_maker("tensorboard", full_path=True), ["GET", "POST"])


@router.get("/train-monitor")
async def train_monitor_redirect():
    return RedirectResponse("/train-monitor/", status_code=307)


router.add_route("/train-monitor/{path:path}", reverse_proxy_maker("monitor"), ["GET"])

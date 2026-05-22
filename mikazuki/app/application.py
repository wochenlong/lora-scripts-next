import asyncio
import mimetypes
import os
import sys
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from starlette.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from mikazuki.app.config import app_config
from mikazuki.app.api import load_schemas, load_presets
from mikazuki.app.api import router as api_router
# from mikazuki.app.ipc import router as ipc_router
from mikazuki.app.proxy import router as proxy_router
from mikazuki.utils.devices import check_torch_gpu

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


def frontend_dist_path() -> Path:
    frontend_dist = Path(os.environ.get("MIKAZUKI_FRONTEND_DIST", "frontend/dist"))
    if not frontend_dist.is_absolute():
        frontend_dist = Path.cwd() / frontend_dist
    return frontend_dist


_FRONTEND_DIST = frontend_dist_path()
_DEFAULT_START_PAGE = "/lora/sd3.html"


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as ex:
            if ex.status_code == 404:
                return await super().get_response("index.html", scope)
            else:
                raise ex


_BROWSER_CANDIDATES = {
    "chrome": [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ],
    "edge": [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ],
}


def _resolve_browser():
    """Resolve --browser shortcut (chrome/edge) to a webbrowser controller."""
    name = os.environ.get("MIKAZUKI_BROWSER", "").lower()
    if not name or name == "default":
        return webbrowser
    candidates = _BROWSER_CANDIDATES.get(name, [])
    for path in candidates:
        if os.path.isfile(path):
            return webbrowser.get(f'"{path}" %s')
    return webbrowser


def _start_url() -> str:
    page = os.environ.get("MIKAZUKI_START_PAGE", _DEFAULT_START_PAGE).strip() or _DEFAULT_START_PAGE
    if not page.startswith("/"):
        page = f"/{page}"
    return f'http://{os.environ["MIKAZUKI_HOST"]}:{os.environ["MIKAZUKI_PORT"]}{page}'


async def _async_update_check():
    from mikazuki.update_check import check_update, log_update_notice
    try:
        await asyncio.to_thread(check_update)
        log_update_notice()
    except Exception:
        pass


async def app_startup():
    app_config.load_config()

    await load_schemas()
    await load_presets()
    await asyncio.to_thread(check_torch_gpu)

    asyncio.create_task(_async_update_check())

    if sys.platform == "win32" and os.environ.get("MIKAZUKI_DEV", "0") != "1":
        import time
        from mikazuki.log import log as app_log

        browser = _resolve_browser()
        if browser is not webbrowser:
            app_log.info(f"Using browser: {os.environ.get('MIKAZUKI_BROWSER', 'default')}")

        browser.open(_start_url())
        monitor_port = os.environ.get("TRAIN_MONITOR_PORT", "6008")
        time.sleep(1)
        app_log.info(f"Opening train monitor in browser: http://127.0.0.1:{monitor_port}")
        browser.open(f'http://127.0.0.1:{monitor_port}')


@asynccontextmanager
async def lifespan(app: FastAPI):
    await app_startup()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(proxy_router)


cors_config = os.environ.get("MIKAZUKI_APP_CORS", "")
if cors_config != "":
    if cors_config == "1":
        cors_config = ["http://localhost:8004", "*"]
    else:
        cors_config = cors_config.split(";")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_config,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def redirect_vuepress_md_to_html(request, call_next):
    """VuePress sidebar links use *.md; vendored dist only ships *.html."""
    path = request.url.path
    if request.method == "GET" and path.endswith(".md"):
        html_path = f"{path[:-3]}.html"
        rel = html_path.lstrip("/")
        if (_FRONTEND_DIST / rel).is_file():
            query = request.url.query
            target = f"{html_path}?{query}" if query else html_path
            return RedirectResponse(url=target, status_code=302)
    return await call_next(request)


@app.middleware("http")
async def add_cache_control_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "max-age=0"
    return response


_TAGGER_PROGRESS_SCRIPT_TAG = b'<script src="/assets/tagger_progress.js"></script>'


@app.middleware("http")
async def inject_tagger_progress_script(request, call_next):
    """Inject progress UI script into all HTML shells (VuePress SPA entry pages)."""
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or "text/html" not in content_type:
        return response
    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    if _TAGGER_PROGRESS_SCRIPT_TAG not in body:
        import re
        if re.search(rb"<body[^>]*>", body):
            body = re.sub(
                rb"(<body[^>]*>)",
                rb"\1\n" + _TAGGER_PROGRESS_SCRIPT_TAG,
                body,
                count=1,
            )
        elif b"</body>" in body:
            body = body.replace(b"</body>", _TAGGER_PROGRESS_SCRIPT_TAG + b"\n</body>", 1)
    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(content=body, status_code=response.status_code, headers=headers, media_type="text/html")

app.include_router(api_router, prefix="/api")
# app.include_router(ipc_router, prefix="/ipc")

_TRAIN_LOG_HTML = Path(__file__).resolve().parent.parent / "static" / "train_log.html"
_TAGGER_PROGRESS_JS = Path(__file__).resolve().parent.parent / "static" / "tagger_progress.js"


@app.get("/assets/tagger_progress.js")
async def tagger_progress_script():
    if not _TAGGER_PROGRESS_JS.is_file():
        raise HTTPException(status_code=404, detail="tagger_progress.js not found")
    return FileResponse(str(_TAGGER_PROGRESS_JS), media_type="application/javascript")


@app.get("/train-log")
async def train_log_viewer():
    """Fullscreen training log viewer (SSE). Embed: <iframe src="/train-log?task_id=…" />."""
    if not _TRAIN_LOG_HTML.is_file():
        raise HTTPException(status_code=404, detail="train_log.html not found")
    return FileResponse(str(_TRAIN_LOG_HTML))


@app.get("/lora/sdxl.html")
async def lora_sdxl_redirect():
    """Legacy SDXL page → unified Stable Diffusion (master) entry."""
    return RedirectResponse(url="/lora/master.html", status_code=302)


@app.get("/")
async def index():
    return FileResponse(str(_FRONTEND_DIST / "index.html"))


@app.get("/favicon.ico", response_class=FileResponse)
async def favicon():
    return FileResponse("assets/favicon.ico")

app.mount("/", SPAStaticFiles(directory=str(_FRONTEND_DIST), html=True), name="static")

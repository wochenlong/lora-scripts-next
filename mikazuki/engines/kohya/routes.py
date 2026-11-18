"""kohya engine routes (mounted at /api/engines/kohya/*)."""

import asyncio

from mikazuki.app.models import APIResponseSuccess, APIResponseFail
from mikazuki.download_sources import resolve_download_sources, DownloadSources
from .settings import runtime
from .extension_state import read_status
from .installer import start_install, installation_plan, remove_extension, start_upgrade, start_main_env_upgrade
from .manifest import TRAIN_TYPES
from .preflight import check_runtime


async def status():
    # A cache-miss fallback audit spawns a python subprocess importing torch;
    # keep that off the event loop.
    data = await asyncio.to_thread(read_status, runtime())
    data["train_types"] = sorted(TRAIN_TYPES)
    return APIResponseSuccess(data=data)


async def preflight(config):
    try:
        rt = runtime()
        await asyncio.to_thread(check_runtime, rt)
        return APIResponseSuccess(data={"ok": True, "errors": [], "warnings": [], "facts": {}})
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc), data={"ok": False, "errors": [str(exc)]})


async def install(payload, force_install=False):
    rt = runtime()
    sources = resolve_download_sources(payload) or DownloadSources()
    if payload.get("dry_run", True):
        return APIResponseSuccess(data={"plan": installation_plan(rt, sources)})
    current = await asyncio.to_thread(read_status, rt)
    if not force_install and current["state"] == "ready":
        return APIResponseSuccess(data={"already_ready": True, "status": current})
    try:
        return APIResponseSuccess(data=start_install(rt, sources, repair=force_install))
    except ValueError as exc:
        return APIResponseFail(message=str(exc))


async def repair(payload):
    return await install(payload, force_install=True)


async def upgrade(payload):
    """Incremental per-pin upgrade ("需要升级" path): never recreates the env,
    only installs packages that violate the current pins. Works for both the
    standalone venv and a legacy main environment."""
    rt = runtime()
    status = await asyncio.to_thread(read_status, rt)
    if status["state"] != "ready":
        return APIResponseFail(message="环境未就绪，无法增量升级；请先安装或修复。")
    drift = status["facts"].get("drift") or []
    if not drift:
        return APIResponseSuccess(data={"already_up_to_date": True, "status": status})
    sources = resolve_download_sources(payload) or DownloadSources()
    try:
        if status["facts"].get("mode") == "main_env":
            result = start_main_env_upgrade(rt, status["runtime"]["python"], sources, drift)
        else:
            result = start_upgrade(rt, sources, drift)
    except ValueError as exc:
        return APIResponseFail(message=str(exc))
    return APIResponseSuccess(data=result)


async def uninstall():
    try:
        remove_extension(runtime())
        return APIResponseSuccess(data={"status": await asyncio.to_thread(read_status, runtime())})
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc))

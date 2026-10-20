"""Lifecycle, preflight and dry-run routes."""
from mikazuki.app.models import APIResponseFail, APIResponseSuccess
from mikazuki.download_sources import DownloadSources, resolve_download_sources
from .extension_state import check_runtime, read_status
from .installer import installation_plan, remove_extension, start_install
from .settings import feature_enabled, runtime


async def status():
    import asyncio
    return APIResponseSuccess(data=await asyncio.to_thread(read_status, runtime()))


async def install(payload, force_install=False):
    if not feature_enabled():
        return APIResponseFail(message="KohakuMossTrainer 已被禁用。")
    payload = payload or {}
    rt = runtime()
    sources = resolve_download_sources(payload) or DownloadSources()
    try:
        if payload.get("dry_run", True):
            return APIResponseSuccess(data={"plan": installation_plan(rt, sources), "repair": force_install})
        current = read_status(rt)
        if current["state"] == "ready" and not force_install:
            return APIResponseSuccess(data={"already_ready": True, "status": current})
        return APIResponseSuccess(data=start_install(rt, sources, repair=force_install))
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc))


async def repair(payload):
    return await install({"dry_run": False, **(payload or {})}, force_install=True)


async def uninstall():
    try:
        rt = runtime()
        remove_extension(rt)
        return APIResponseSuccess(data={"status": read_status(rt)})
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc))


async def preflight(config):
    from .preflight import run_preflight
    try:
        rt = runtime()
        check_runtime(rt)
        result = run_preflight(config, rt)
        if not result["ok"]:
            return APIResponseFail(message="; ".join(result["errors"]), data=result)
        return APIResponseSuccess(data=result)
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc), data={"ok": False, "errors": [str(exc)]})


async def dry_run(config):
    from .run import build_dry_run
    result = build_dry_run(config, runtime())
    if not result["ok"]:
        return APIResponseFail(message="; ".join(result["errors"]), data=result)
    return APIResponseSuccess(data=result)

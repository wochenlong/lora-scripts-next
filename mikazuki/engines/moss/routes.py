"""Native engine endpoints; read-only dry runs never install or launch jobs."""
from mikazuki.app.models import APIResponseFail, APIResponseSuccess
from mikazuki.download_sources import DownloadSources, parse_download_sources
from .extension_state import check_runtime, read_status
from .installer import installation_plan, remove_extension, start_install
from .settings import feature_enabled, runtime


async def status():
    return APIResponseSuccess(data=read_status(runtime()))


async def install(payload, force_install=False):
    if not feature_enabled():
        return APIResponseFail(message="MOSS 已被禁用。")
    payload = payload or {}
    rt = runtime()
    sources = parse_download_sources(payload) or DownloadSources()
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
    # Repair is an explicit rebuild of the three managed runtime directories.
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
        if not result.get("ok"):
            return APIResponseFail(message="; ".join(result.get("errors") or []), data=result)
        return APIResponseSuccess(data=result)
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc), data={"ok": False, "errors": [str(exc)], "warnings": [], "facts": {}})


async def dry_run(config):
    from .run import build_dry_run

    try:
        result = build_dry_run(config, runtime())
        if not result.get("ok", True):
            return APIResponseFail(message="; ".join(result.get("errors") or []), data=result)
        return APIResponseSuccess(data=result)
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc))

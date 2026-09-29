"""kohya engine routes (mounted at /api/engines/kohya/*)."""

from mikazuki.app.models import APIResponseSuccess, APIResponseFail
from mikazuki.download_sources import parse_download_sources, DownloadSources
from .settings import runtime
from .extension_state import read_status
from .installer import start_install, installation_plan, remove_extension
from .manifest import TRAIN_TYPES
from .preflight import check_runtime


async def status():
    data = read_status(runtime())
    data["train_types"] = sorted(TRAIN_TYPES)
    return APIResponseSuccess(data=data)


async def preflight(config):
    try:
        rt = runtime()
        check_runtime(rt)
        return APIResponseSuccess(data={"ok": True, "errors": [], "warnings": [], "facts": {}})
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc), data={"ok": False, "errors": [str(exc)]})


async def install(payload, force_install=False):
    rt = runtime()
    sources = parse_download_sources(payload) or DownloadSources()
    if payload.get("dry_run", True):
        return APIResponseSuccess(data={"plan": installation_plan(rt, sources)})
    if not force_install and read_status(rt)["state"] == "ready":
        return APIResponseSuccess(data={"already_ready": True, "status": read_status(rt)})
    try:
        return APIResponseSuccess(data=start_install(rt, sources, repair=force_install))
    except ValueError as exc:
        return APIResponseFail(message=str(exc))


async def repair(payload):
    return await install(payload, force_install=True)


async def uninstall():
    try:
        remove_extension(runtime())
        return APIResponseSuccess(data={"status": read_status(runtime())})
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc))

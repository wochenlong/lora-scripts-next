import uuid

from mikazuki.app.models import APIResponseSuccess, APIResponseFail
from mikazuki.download_sources import parse_download_sources, DownloadSources
from .settings import runtime, feature_enabled
from .extension_state import read_status
from .installer import start_install, installation_plan, remove_extension
from .adapter import adapt_config, dump_config
from .launcher import build_train_spec
from .preflight import check_runtime


async def status():
    return APIResponseSuccess(data=read_status(runtime()))


async def preflight(config):
    try:
        rt = runtime()
        check_runtime(rt)
        adapted = adapt_config(config, rt)
        build_train_spec(rt, "preflight.json", config.get("gpu_ids"))
        return APIResponseSuccess(data={"ok": True, "errors": [], "warnings": [], "facts": {"images_with_repeats": len(adapted.dataset)}})
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc), data={"ok": False, "errors": [str(exc)]})


async def dry_run(config):
    """Render official argv and manifests without creating a training task."""
    try:
        rt = runtime()
        adapted = adapt_config(config, rt)
        path = dump_config(adapted, rt.project_root / "config/autosave", f"diffsynth-dry-{uuid.uuid4().hex[:8]}")
        spec = build_train_spec(rt, path, config.get("gpu_ids"))
        return APIResponseSuccess(data={"command": spec.command, "cwd": str(spec.cwd), "engine_config_path": str(path), "config": adapted.arguments})
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc))


async def install(payload, force_install=False):
    if not feature_enabled():
        return APIResponseFail(message="DiffSynth 已被禁用。")
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

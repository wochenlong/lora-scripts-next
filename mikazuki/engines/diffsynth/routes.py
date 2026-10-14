import uuid

from mikazuki.app.models import APIResponseSuccess, APIResponseFail
from mikazuki.download_sources import parse_download_sources, DownloadSources
from .settings import runtime, feature_enabled
from .extension_state import read_status
from .diagnose import diagnose as diagnose_runtime
from .installer import (
    start_install,
    start_surgical_repair,
    start_full_reinstall,
    installation_plan,
    remove_extension,
)
from .adapter import adapt_config, dump_config
from .launcher import build_train_spec
from .preflight import check_runtime


async def status():
    rt = runtime()
    data = read_status(rt)
    if data.get("state") in {"broken", "not_installed", "installed_unverified"}:
        try:
            data["diagnosis"] = diagnose_runtime(rt)
        except Exception as exc:  # noqa: BLE001
            data["diagnosis"] = {
                "code": "diagnose_failed",
                "severity": "error",
                "summary": "诊断失败",
                "detail": str(exc),
                "recommended_actions": ["full_reinstall"] if data.get("state") == "broken" else [],
                "allows_full_reinstall": data.get("state") == "broken",
                "components": {},
            }
    return APIResponseSuccess(data=data)


async def diagnose():
    """GET /engines/diffsynth/diagnose"""
    return APIResponseSuccess(data=diagnose_runtime(runtime()))


async def preflight(config):
    try:
        rt = runtime()
        check_runtime(rt)
        adapted = adapt_config(config, rt)
        build_train_spec(rt, "preflight.json", config.get("gpu_ids"))
        return APIResponseSuccess(
            data={"ok": True, "errors": [], "warnings": [], "facts": {"images_with_repeats": len(adapted.dataset)}}
        )
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc), data={"ok": False, "errors": [str(exc)]})


async def dry_run(config):
    """Render official argv and manifests without creating a training task."""
    try:
        rt = runtime()
        adapted = adapt_config(config, rt)
        path = dump_config(adapted, rt.project_root / "config/autosave", f"diffsynth-dry-{uuid.uuid4().hex[:8]}")
        spec = build_train_spec(rt, path, config.get("gpu_ids"))
        return APIResponseSuccess(
            data={
                "command": spec.command,
                "cwd": str(spec.cwd),
                "engine_config_path": str(path),
                "config": adapted.arguments,
            }
        )
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc))


async def install(payload, force_install=False):
    if not feature_enabled():
        return APIResponseFail(message="DiffSynth 已被禁用。")
    rt = runtime()
    sources = parse_download_sources(payload) or DownloadSources()
    if payload.get("dry_run", True):
        return APIResponseSuccess(data={"plan": installation_plan(rt, sources)})
    if force_install:
        # Legacy callers used install(force) as wipe-reinstall; keep that meaning.
        try:
            return APIResponseSuccess(data=start_full_reinstall(rt, sources))
        except ValueError as exc:
            return APIResponseFail(message=str(exc))
    if read_status(rt)["state"] == "ready":
        return APIResponseSuccess(data={"already_ready": True, "status": read_status(rt)})
    try:
        return APIResponseSuccess(data=start_install(rt, sources, repair=False))
    except ValueError as exc:
        return APIResponseFail(message=str(exc))


async def repair(payload):
    """Surgical repair by default (#462). Use action=full_reinstall for wipe."""
    if not feature_enabled():
        return APIResponseFail(message="DiffSynth 已被禁用。")
    rt = runtime()
    sources = parse_download_sources(payload) or DownloadSources()
    action = (payload or {}).get("action")
    dry_run_flag = bool((payload or {}).get("dry_run", False))
    if action == "full_reinstall" or (payload or {}).get("full_reinstall"):
        if dry_run_flag:
            from .installer import build_repair_plan

            plan = build_repair_plan(rt, sources, ["full_reinstall"])
            return APIResponseSuccess(data={"dry_run": True, "plan": plan})
        try:
            return APIResponseSuccess(data=start_full_reinstall(rt, sources))
        except ValueError as exc:
            return APIResponseFail(message=str(exc))
    try:
        return APIResponseSuccess(
            data=start_surgical_repair(
                rt,
                sources,
                action=action if action and action != "auto" else None,
                dry_run=dry_run_flag,
            )
        )
    except ValueError as exc:
        return APIResponseFail(message=str(exc))


async def uninstall():
    try:
        remove_extension(runtime())
        return APIResponseSuccess(data={"status": read_status(runtime())})
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc))

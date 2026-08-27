"""Anima Fast engine routes (mounted at /api/engines/anima-fast/*)."""

import os

from datetime import datetime
from pathlib import Path

from mikazuki.app.models import APIResponseFail, APIResponseSuccess
from mikazuki.engines.anima_fast.adapter import AdapterError, adapt_config
from mikazuki.engines.anima_fast.environment import start_install_task
from mikazuki.engines.anima_fast.extension_state import (
    STATE_READY,
    default_layout,
    read_extension_status,
    write_install_state,
)
from mikazuki.engines.anima_fast.installer import build_install_plan, remove_extension
from mikazuki.engines.anima_fast.manifest import UPSTREAM
from mikazuki.engines.anima_fast.preflight import run_preflight
from mikazuki.engines.anima_fast.preview import apply_anima_fast_preview
from mikazuki.engines.anima_fast.settings import feature_enabled
from mikazuki.engines.anima_fast.source_root import InstallSourceError, resolve_install_source_root
from mikazuki.engines.anima_fast.run import (
    anima_fast_disabled_response,
    anima_fast_fail_from_preflight,
    anima_fast_runtime,
    write_anima_fast_toml,
)


async def status():
    layout = default_layout(Path.cwd())
    data = read_extension_status(layout).as_dict()
    runtime = anima_fast_runtime()
    runtime_available = runtime.python.is_file() and (runtime.anima_root / "train.py").is_file()
    data["feature_enabled"] = feature_enabled()
    data["runtime"] = {
        "anima_root": str(runtime.anima_root),
        "source_commit": runtime.source_commit,
        "python": str(runtime.python),
        "output_dir": str(runtime.output_dir),
        "logging_dir": str(runtime.logging_dir),
        "cache_dir": str(runtime.cache_dir),
        "external_runtime_exists": runtime_available,
    }
    return APIResponseSuccess(data=data)


async def preflight(config: dict):
    runtime = anima_fast_runtime()
    autosave_dir = os.path.join(os.getcwd(), "config", "autosave")
    os.makedirs(autosave_dir, exist_ok=True)
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-anima-fast"
    try:
        preview_warnings = apply_anima_fast_preview(config, autosave_dir, run_id)
        adapted = adapt_config(config, runtime, run_id)
    except AdapterError as exc:
        return APIResponseFail(message=str(exc))
    result = run_preflight(adapted.values, runtime)
    result.warnings = [*adapted.warnings, *preview_warnings, *result.warnings]
    if result.ok:
        return APIResponseSuccess(data=result.as_dict())
    return anima_fast_fail_from_preflight(result)


async def dry_run(config: dict):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    autosave_dir = os.path.join(os.getcwd(), "config", "autosave")
    os.makedirs(autosave_dir, exist_ok=True)
    config.pop("gpu_ids", None)
    config.pop("model_train_type", None)
    try:
        toml_file, adapted_values, warnings = write_anima_fast_toml(config, timestamp, autosave_dir)
    except AdapterError as exc:
        return APIResponseFail(message=str(exc))
    return APIResponseSuccess(data={
        "toml_path": str(toml_file),
        "config": adapted_values,
        "warnings": warnings,
    })


async def install(payload: dict, force_install: bool = False):
    if not feature_enabled():
        return anima_fast_disabled_response()
    runtime = anima_fast_runtime()
    source_commit = str(payload.get("source_commit") or runtime.source_commit or "").strip() or UPSTREAM["commit"] or None
    dry_run = payload.get("dry_run", True) is not False
    project_root = Path.cwd()
    layout = default_layout(project_root)
    current_status = read_extension_status(layout)
    if not dry_run and not force_install and current_status.state == STATE_READY:
        return APIResponseSuccess(data={
            "already_ready": True,
            "status": current_status.as_dict(),
            "message": "Anima Fast plugin is already ready",
        })
    explicit = payload.get("source_root") or os.environ.get("ANIMA_LORA_ROOT")
    try:
        source_root = resolve_install_source_root(
            project_root,
            Path(explicit) if explicit else None,
            source_commit,
            allow_clone=False,
        )
    except InstallSourceError as exc:
        return APIResponseFail(message=str(exc))
    plan = build_install_plan(source_root, layout, dry_run=dry_run, source_commit=source_commit)
    data = {"plan": plan.as_dict()}
    if dry_run:
        data["message"] = "Installer dry-run completed"
        return APIResponseSuccess(data=data)
    try:
        from mikazuki.download_sources import parse_download_sources

        task_id, install_data = start_install_task(
            Path.cwd(),
            layout,
            source_root,
            dry_run=False,
            source_commit=source_commit,
            download_sources=parse_download_sources(payload),
        )
    except Exception as exc:
        write_install_state(layout, "broken", {"plan": plan.as_dict()}, str(exc))
        return APIResponseFail(message=f"Anima LoRA install failed: {exc}")
    data.update(install_data)
    data["status"] = read_extension_status(layout).as_dict()
    data["message"] = "Anima LoRA install task started"
    return APIResponseSuccess(data=data)


async def repair(payload: dict):
    return await install(payload, force_install=True)


async def uninstall():
    if not feature_enabled():
        return anima_fast_disabled_response()
    layout = default_layout(Path.cwd())
    try:
        remove_extension(layout, Path.cwd())
    except Exception as exc:
        return APIResponseFail(message=f"Anima LoRA uninstall failed: {exc}")
    return APIResponseSuccess(data={"status": read_extension_status(layout).as_dict()})

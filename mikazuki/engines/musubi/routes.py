"""musubi-tuner engine routes (mounted at /api/engines/musubi/*)."""

import os

from datetime import datetime
from pathlib import Path

from mikazuki.app.models import APIResponseFail, APIResponseSuccess
from mikazuki.engines.musubi import TRAIN_TYPE as MUSUBI_TRAIN_TYPE
from mikazuki.engines.musubi.adapter import (
    AdapterError as MusubiAdapterError,
    adapt_config as adapt_musubi_config,
    dump_dataset_toml as dump_musubi_dataset_toml,
    dump_train_toml as dump_musubi_train_toml,
)
from mikazuki.engines.musubi.environment import start_install_task as start_musubi_install_task
from mikazuki.engines.musubi.extension_state import (
    STATE_READY as MUSUBI_STATE_READY,
    default_layout as musubi_default_layout,
    read_extension_status as read_musubi_extension_status,
    write_install_state as write_musubi_install_state,
)
from mikazuki.engines.musubi.installer import (
    build_install_plan as build_musubi_install_plan,
    remove_extension as remove_musubi_extension,
)
from mikazuki.engines.musubi.preflight import run_preflight as run_musubi_preflight
from mikazuki.engines.musubi.run import (
    musubi_disabled_response,
    musubi_fail_from_preflight,
    musubi_runtime,
)
from mikazuki.engines.musubi.settings import (
    default_upstream_cache as musubi_default_upstream_cache,
    feature_enabled as musubi_feature_enabled,
    resolve_install_source_root as resolve_musubi_install_source_root,
)


async def status():
    layout = musubi_default_layout(Path.cwd())
    data = read_musubi_extension_status(layout).as_dict()
    runtime = musubi_runtime()
    data["feature_enabled"] = musubi_feature_enabled()
    data["train_type"] = MUSUBI_TRAIN_TYPE
    data["runtime"] = {
        "musubi_root": str(runtime.musubi_root),
        "python": str(runtime.python),
        "output_dir": str(runtime.output_dir),
        "logging_dir": str(runtime.logging_dir),
        "cache_dir": str(runtime.cache_dir),
        "external_runtime_exists": runtime.python.is_file()
        and (runtime.musubi_root / "src" / "musubi_tuner").is_dir(),
    }
    return APIResponseSuccess(data=data)


async def preflight(config: dict):
    if not musubi_feature_enabled():
        return musubi_disabled_response()
    runtime = musubi_runtime()
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-musubi"
    try:
        adapted = adapt_musubi_config(config, runtime, run_id)
    except MusubiAdapterError as exc:
        return APIResponseFail(message=str(exc))
    result = run_musubi_preflight(adapted.values, runtime, adapted.dataset)
    result.warnings = [*adapted.warnings, *result.warnings]
    if result.ok:
        return APIResponseSuccess(data=result.as_dict())
    return musubi_fail_from_preflight(result)


async def dry_run(config: dict):
    if not musubi_feature_enabled():
        return musubi_disabled_response()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    autosave_dir = os.path.join(os.getcwd(), "config", "autosave")
    os.makedirs(autosave_dir, exist_ok=True)
    config.pop("gpu_ids", None)
    config.pop("model_train_type", None)
    runtime = musubi_runtime()
    run_id = f"{timestamp}-musubi"
    try:
        adapted = adapt_musubi_config(config, runtime, run_id)
    except MusubiAdapterError as exc:
        return APIResponseFail(message=str(exc))
    toml_file_path = Path(autosave_dir) / f"{run_id}.toml"
    dataset_file_path = Path(autosave_dir) / f"{run_id}-dataset.toml"
    dataset_file_path.write_text(dump_musubi_dataset_toml(adapted.dataset), encoding="utf-8")
    adapted.values["dataset_config"] = dataset_file_path.resolve().as_posix()
    toml_file_path.write_text(dump_musubi_train_toml(adapted.values), encoding="utf-8")
    return APIResponseSuccess(data={
        "toml_path": str(toml_file_path),
        "dataset_toml_path": str(dataset_file_path),
        "config": adapted.values,
        "dataset": adapted.dataset,
        "warnings": adapted.warnings,
    })


async def install(payload: dict, force_install: bool = False):
    if not musubi_feature_enabled():
        return musubi_disabled_response()
    source_commit = str(payload.get("source_commit") or "").strip() or None
    cuda_extra = str(payload.get("cuda_extra") or "").strip() or None
    dry_run = payload.get("dry_run", True) is not False
    project_root = Path.cwd()
    layout = musubi_default_layout(project_root)
    current_status = read_musubi_extension_status(layout)
    if not dry_run and not force_install and current_status.state == MUSUBI_STATE_READY:
        return APIResponseSuccess(data={
            "already_ready": True,
            "status": current_status.as_dict(),
            "message": "musubi-tuner plugin is already ready",
        })
    explicit = payload.get("source_root")
    try:
        source_root = resolve_musubi_install_source_root(
            project_root, Path(str(explicit)) if explicit else None, source_commit
        )
    except ValueError as exc:
        if dry_run:
            return APIResponseFail(message=str(exc))
        # Real install: let the background task auto-clone upstream into the cache
        # (mirrors the Anima Fast installer) so clone output streams to the install log.
        source_root = musubi_default_upstream_cache(project_root)
    plan = build_musubi_install_plan(source_root, layout, dry_run=dry_run, source_commit=source_commit)
    data = {"plan": plan.as_dict()}
    if dry_run:
        data["message"] = "Installer dry-run completed"
        return APIResponseSuccess(data=data)
    try:
        from mikazuki.download_sources import parse_download_sources

        task_id, install_data = start_musubi_install_task(
            project_root,
            layout,
            source_root,
            dry_run=False,
            source_commit=source_commit,
            cuda_extra=cuda_extra,
            download_sources=parse_download_sources(payload),
        )
    except Exception as exc:
        write_musubi_install_state(layout, "broken", {"plan": plan.as_dict()}, str(exc))
        return APIResponseFail(message=f"musubi-tuner install failed: {exc}")
    data.update(install_data)
    data["status"] = read_musubi_extension_status(layout).as_dict()
    data["message"] = "musubi-tuner install task started"
    return APIResponseSuccess(data=data)


async def repair(payload: dict):
    return await install(payload, force_install=True)


async def uninstall():
    if not musubi_feature_enabled():
        return musubi_disabled_response()
    layout = musubi_default_layout(Path.cwd())
    try:
        remove_musubi_extension(layout, Path.cwd())
    except Exception as exc:
        return APIResponseFail(message=f"musubi-tuner uninstall failed: {exc}")
    return APIResponseSuccess(data={"status": read_musubi_extension_status(layout).as_dict()})

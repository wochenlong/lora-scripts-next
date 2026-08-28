"""ai-toolkit engine routes (mounted at /api/engines/ai-toolkit/*)."""

import os

from datetime import datetime
from pathlib import Path

from mikazuki.app.models import APIResponseFail, APIResponseSuccess
from mikazuki.engines.ai_toolkit import TRAIN_TYPE_MAP as AI_TOOLKIT_TRAIN_TYPE_MAP
from mikazuki.engines.ai_toolkit.manifest import UPSTREAM
from mikazuki.engines.ai_toolkit.adapter import (
    AdapterError as AiToolkitAdapterError,
    VARIANTS,
    adapt_config as adapt_ai_toolkit_config,
    dump_yaml as dump_ai_toolkit_yaml,
)
from mikazuki.engines.ai_toolkit.environment import start_install_task as start_ai_toolkit_install_task
from mikazuki.engines.ai_toolkit.extension_state import (
    STATE_READY as AI_TOOLKIT_STATE_READY,
    default_layout as ai_toolkit_default_layout,
    read_extension_status as read_ai_toolkit_extension_status,
    write_install_state as write_ai_toolkit_install_state,
)
from mikazuki.engines.ai_toolkit.installer import (
    build_install_plan as build_ai_toolkit_install_plan,
    remove_extension as remove_ai_toolkit_extension,
)
from mikazuki.engines.ai_toolkit.preflight import run_preflight as run_ai_toolkit_preflight
from mikazuki.engines.ai_toolkit.run import (
    ai_toolkit_disabled_response,
    ai_toolkit_fail_from_preflight,
    ai_toolkit_runtime,
)
from mikazuki.engines.ai_toolkit.settings import (
    default_upstream_cache as ai_toolkit_default_upstream_cache,
    feature_enabled as ai_toolkit_feature_enabled,
    resolve_install_source_root as resolve_ai_toolkit_install_source_root,
)


def _resolve_variant(payload: dict) -> str:
    train_type = str(payload.get("model_train_type") or "").strip()
    if train_type in AI_TOOLKIT_TRAIN_TYPE_MAP:
        return AI_TOOLKIT_TRAIN_TYPE_MAP[train_type]
    variant = str(payload.get("model_version") or "").strip()
    return variant if variant in VARIANTS else "klein-4b"


async def status():
    layout = ai_toolkit_default_layout(Path.cwd())
    data = read_ai_toolkit_extension_status(layout).as_dict()
    runtime = ai_toolkit_runtime()
    data["feature_enabled"] = ai_toolkit_feature_enabled()
    data["train_types"] = list(AI_TOOLKIT_TRAIN_TYPE_MAP)
    data["runtime"] = {
        "toolkit_root": str(runtime.toolkit_root),
        "python": str(runtime.python),
        "output_dir": str(runtime.output_dir),
        "logging_dir": str(runtime.logging_dir),
        "cache_dir": str(runtime.cache_dir),
        "external_runtime_exists": runtime.python.is_file()
        and (runtime.toolkit_root / "run.py").is_file()
        and (runtime.toolkit_root / "toolkit").is_dir(),
    }
    return APIResponseSuccess(data=data)


async def preflight(config: dict):
    if not ai_toolkit_feature_enabled():
        return ai_toolkit_disabled_response()
    runtime = ai_toolkit_runtime()
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-ai-toolkit"
    variant = _resolve_variant(config)
    try:
        adapted = adapt_ai_toolkit_config(config, runtime, run_id, variant)
    except AiToolkitAdapterError as exc:
        return APIResponseFail(message=str(exc))
    result = run_ai_toolkit_preflight(adapted.config, runtime, variant, te_path=adapted.te_path)
    result.warnings = [*adapted.warnings, *result.warnings]
    if result.ok:
        return APIResponseSuccess(data=result.as_dict())
    return ai_toolkit_fail_from_preflight(result)


async def dry_run(config: dict):
    if not ai_toolkit_feature_enabled():
        return ai_toolkit_disabled_response()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    autosave_dir = os.path.join(os.getcwd(), "config", "autosave")
    os.makedirs(autosave_dir, exist_ok=True)
    config = dict(config)
    config.pop("gpu_ids", None)
    variant = _resolve_variant(config)
    runtime = ai_toolkit_runtime()
    run_id = f"{timestamp}-ai-toolkit"
    try:
        adapted = adapt_ai_toolkit_config(config, runtime, run_id, variant)
    except AiToolkitAdapterError as exc:
        return APIResponseFail(message=str(exc))
    yaml_file_path = Path(autosave_dir) / f"{run_id}.yaml"
    yaml_file_path.write_text(dump_ai_toolkit_yaml(adapted.config), encoding="utf-8")
    return APIResponseSuccess(data={
        "yaml_path": str(yaml_file_path),
        "variant": variant,
        "config": adapted.config,
        "warnings": adapted.warnings,
    })


async def install(payload: dict, force_install: bool = False):
    if not ai_toolkit_feature_enabled():
        return ai_toolkit_disabled_response()
    source_commit = str(payload.get("source_commit") or "").strip() or UPSTREAM["commit"] or None
    cuda_extra = str(payload.get("cuda_extra") or "").strip() or None
    dry_run = payload.get("dry_run", True) is not False
    project_root = Path.cwd()
    layout = ai_toolkit_default_layout(project_root)
    current_status = read_ai_toolkit_extension_status(layout)
    if not dry_run and not force_install and current_status.state == AI_TOOLKIT_STATE_READY:
        return APIResponseSuccess(data={
            "already_ready": True,
            "status": current_status.as_dict(),
            "message": "ai-toolkit plugin is already ready",
        })
    explicit = payload.get("source_root")
    try:
        source_root = resolve_ai_toolkit_install_source_root(
            project_root, Path(str(explicit)) if explicit else None, source_commit
        )
    except ValueError as exc:
        if dry_run:
            return APIResponseFail(message=str(exc))
        source_root = ai_toolkit_default_upstream_cache(project_root)
    plan = build_ai_toolkit_install_plan(source_root, layout, dry_run=dry_run, source_commit=source_commit)
    data = {"plan": plan.as_dict()}
    if dry_run:
        data["message"] = "Installer dry-run completed"
        return APIResponseSuccess(data=data)
    try:
        from mikazuki.download_sources import parse_download_sources

        task_id, install_data = start_ai_toolkit_install_task(
            project_root,
            layout,
            source_root,
            dry_run=False,
            source_commit=source_commit,
            cuda_extra=cuda_extra,
            download_sources=parse_download_sources(payload),
        )
    except Exception as exc:
        write_ai_toolkit_install_state(layout, "broken", {"plan": plan.as_dict()}, str(exc))
        return APIResponseFail(message=f"ai-toolkit install failed: {exc}")
    data.update(install_data)
    data["status"] = read_ai_toolkit_extension_status(layout).as_dict()
    data["message"] = "ai-toolkit install task started"
    return APIResponseSuccess(data=data)


async def repair(payload: dict):
    return await install(payload, force_install=True)


async def uninstall():
    if not ai_toolkit_feature_enabled():
        return ai_toolkit_disabled_response()
    layout = ai_toolkit_default_layout(Path.cwd())
    try:
        remove_ai_toolkit_extension(layout, Path.cwd())
    except Exception as exc:
        return APIResponseFail(message=f"ai-toolkit uninstall failed: {exc}")
    return APIResponseSuccess(data={"status": read_ai_toolkit_extension_status(layout).as_dict()})

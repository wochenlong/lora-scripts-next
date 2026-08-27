"""Anima Fast /api/run handler (gate -> adapt -> preflight -> dump -> launch)."""

import sys

from pathlib import Path

import mikazuki.process as process
from mikazuki.app.models import APIResponseFail
from mikazuki.log import log
from mikazuki.engines.anima_fast.adapter import (
    AdapterError,
    adapt_config,
    dump_fast_dataset_toml,
    dump_flat_toml,
    ensure_fast_run_log_dirs,
)
from mikazuki.engines.anima_fast.environment import audit_environment
from mikazuki.engines.anima_fast.extension_state import (
    STATE_READY,
    default_layout,
    read_extension_status,
    write_install_state,
)
from mikazuki.engines.anima_fast.preflight import run_preflight
from mikazuki.engines.anima_fast.preprocess import prepare_anima_fast_dataset, user_left_resized_empty
from mikazuki.engines.anima_fast.preview import apply_anima_fast_preview
from mikazuki.engines.anima_fast.settings import discover_runtime, feature_enabled
from mikazuki.engines.runner import RunContext


def anima_fast_runtime():
    return discover_runtime(lora_next_root=Path.cwd())


def anima_fast_disabled_response():
    return APIResponseFail(
        message="Anima Fast plugin is temporarily disabled by maintainer (LORA_ENABLE_ANIMA_FAST=0)."
    )


def write_anima_fast_toml(config: dict, timestamp: str, autosave_dir: str) -> tuple[Path, dict, list[str]]:
    runtime = anima_fast_runtime()
    run_id = f"{timestamp}-anima-fast"
    preview_warnings = apply_anima_fast_preview(config, autosave_dir, run_id)
    adapted = adapt_config(config, runtime, run_id)
    warnings = list(adapted.warnings) + preview_warnings
    if user_left_resized_empty(config):
        warnings.append(
            "resized_image_dir 未填写；开始训练时将自动 resize 到 "
            ".cache/anima_fast/<train_data_dir 相对路径>/resized（同一数据集可复用）"
        )
    return write_adapted_anima_fast_toml(adapted.values, warnings, run_id, autosave_dir)


def write_adapted_anima_fast_toml(values: dict, warnings: list[str], run_id: str, autosave_dir: str) -> tuple[Path, dict, list[str]]:
    toml_file = Path(autosave_dir) / f"{run_id}.toml"
    dataset_file = Path(autosave_dir) / f"{run_id}-dataset.toml"
    ensure_fast_run_log_dirs(values)
    values["dataset_config"] = dataset_file.resolve().as_posix()
    dataset_file.write_text(dump_fast_dataset_toml(values), encoding="utf-8")
    toml_file.write_text(dump_flat_toml(values), encoding="utf-8")
    return toml_file, values, warnings


def anima_fast_fail_from_preflight(result):
    errors = list(getattr(result, "errors", None) or [])
    if errors:
        detail = "; ".join(errors[:4])
        if len(errors) > 4:
            detail += f" …（共 {len(errors)} 项）"
        message = f"Anima Fast 预检查失败：{detail}"
    else:
        message = "Anima Fast 预检查失败（未返回具体原因，请修复插件或查看浏览器 Network 响应）"
    return APIResponseFail(message=message, data=result.as_dict())


def anima_fast_ready_gate():
    layout = default_layout(Path.cwd())
    status = read_extension_status(layout)
    if status.state != STATE_READY:
        return False, APIResponseFail(
            message="Anima Fast extension is not ready. Install or repair the extension first.",
            data=status.as_dict(),
        )
    audit = (status.facts or {}).get("audit", {})
    if not audit.get("ok"):
        return False, APIResponseFail(
            message="Anima Fast environment audit has not passed. Repair the extension before training.",
            data=status.as_dict(),
        )
    audit_result = audit_environment(Path.cwd(), layout, main_python=Path(sys.executable), require_cuda=True)
    if not audit_result.ok:
        write_install_state(layout, "broken", {"audit": audit_result.as_dict()}, "; ".join(audit_result.errors))
        return False, APIResponseFail(
            message="Anima Fast environment drift detected. Repair the extension before training.",
            data=audit_result.as_dict(),
        )
    return True, None


def handle_run(config: dict, ctx: RunContext):
    if not feature_enabled():
        return anima_fast_disabled_response()
    ready, failure = anima_fast_ready_gate()
    if not ready:
        return failure
    try:
        runtime = anima_fast_runtime()
        run_id = f"{ctx.timestamp}-anima-fast"
        preview_warnings = apply_anima_fast_preview(config, ctx.autosave_dir, run_id)
        prepared = prepare_anima_fast_dataset(config, runtime, run_id)
        adapted = prepared.adapted
        preflight = run_preflight(adapted.values, runtime)
        if not preflight.ok:
            return anima_fast_fail_from_preflight(preflight)
        toml_file, adapted_values, warnings = write_adapted_anima_fast_toml(
            adapted.values, [*adapted.warnings, *preview_warnings, *preflight.warnings], run_id, ctx.autosave_dir
        )
        metadata = {
            "progress_jsonl": adapted_values.get("progress_jsonl"),
            "output_dir": adapted_values.get("output_dir"),
            "output_name": adapted_values.get("output_name"),
            "logging_dir": adapted_values.get("logging_dir"),
            "warnings": warnings,
            "auto_resized": prepared.auto_resized,
        }
        return process.run_anima_fast_train(str(toml_file), runtime, ctx.gpu_ids, metadata=metadata)
    except AdapterError as exc:
        return APIResponseFail(message=str(exc))
    except Exception as exc:  # noqa: BLE001 - keep API failures structured
        log.error(f"Anima Fast launch failed: {exc}")
        return APIResponseFail(message=f"Anima Fast launch failed: {exc}")

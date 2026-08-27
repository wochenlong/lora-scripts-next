"""musubi-tuner /api/run handler (gate -> adapt -> preflight -> dump -> launch)."""

import os

from pathlib import Path

import mikazuki.process as process
from mikazuki.app.models import APIResponseFail
from mikazuki.app.train_submit import (
    _missing_standard_train_field,
    get_sample_prompts,
    sanitize_config,
    should_generate_sample_prompts,
)
from mikazuki.log import log
from mikazuki.engines.musubi.adapter import (
    AdapterError as MusubiAdapterError,
    adapt_config as adapt_musubi_config,
    dump_dataset_toml as dump_musubi_dataset_toml,
    dump_train_toml as dump_musubi_train_toml,
)
from mikazuki.engines.musubi.environment import audit_environment as audit_musubi_environment
from mikazuki.engines.musubi.extension_state import (
    STATE_READY as MUSUBI_STATE_READY,
    default_layout as musubi_default_layout,
    read_extension_status as read_musubi_extension_status,
    write_install_state as write_musubi_install_state,
)
from mikazuki.engines.musubi.preflight import run_preflight as run_musubi_preflight
from mikazuki.engines.musubi.settings import (
    discover_runtime as discover_musubi_runtime,
    feature_enabled as musubi_feature_enabled,
)
from mikazuki.engines.runner import RunContext
from mikazuki.utils import train_utils


def musubi_runtime():
    return discover_musubi_runtime(lora_next_root=Path.cwd())


def musubi_disabled_response():
    return APIResponseFail(
        message="musubi-tuner backend is temporarily disabled by maintainer (LORA_ENABLE_MUSUBI=0)."
    )


def musubi_ready_gate():
    layout = musubi_default_layout(Path.cwd())
    status = read_musubi_extension_status(layout)
    if status.state != MUSUBI_STATE_READY:
        return False, APIResponseFail(
            message="musubi-tuner 插件未就绪。请先在「设置 → 训练引擎」安装或修复 musubi-tuner 插件。",
            data=status.as_dict(),
        )
    audit = (status.facts or {}).get("audit", {})
    if not audit.get("ok"):
        return False, APIResponseFail(
            message="musubi-tuner 环境审计未通过。请先修复插件再训练。",
            data=status.as_dict(),
        )
    drift = audit_musubi_environment(musubi_runtime())
    if not drift.ok:
        write_musubi_install_state(layout, "broken", {"audit": drift.as_dict()}, "; ".join(drift.errors))
        return False, APIResponseFail(
            message="musubi-tuner 环境发生漂移。请先修复插件再训练。",
            data=drift.as_dict(),
        )
    return True, None


def musubi_fail_from_preflight(result):
    errors = list(getattr(result, "errors", None) or [])
    if errors:
        detail = "; ".join(errors[:4])
        if len(errors) > 4:
            detail += f" …（共 {len(errors)} 项）"
        message = f"musubi-tuner 预检查失败：{detail}"
    else:
        message = "musubi-tuner 预检查失败（未返回具体原因）"
    return APIResponseFail(message=message, data=result.as_dict())


def musubi_apply_sample_defaults(config: dict) -> None:
    """Krea 2 sampling defaults: 1024px; Turbo schedule wants CFG off + few steps."""
    config.setdefault("sample_width", 1024)
    config.setdefault("sample_height", 1024)
    turbo = str(config.get("turbo_dit", "") or "").strip()
    if turbo:
        config.setdefault("sample_cfg", 1)
        config.setdefault("sample_steps", 8)
    else:
        config.setdefault("sample_cfg", 4.5)
        config.setdefault("sample_steps", 28)


def handle_run(config: dict, ctx: RunContext):
    model_train_type = "krea2-lora"
    if not musubi_feature_enabled():
        return musubi_disabled_response()
    ready, failure = musubi_ready_gate()
    if not ready:
        return failure
    try:
        runtime = musubi_runtime()
        train_data_dir = str(config.get("train_data_dir") or "").strip()
        if not train_data_dir:
            return _missing_standard_train_field("train_data_dir", "训练数据集路径")
        if not train_utils.validate_data_dir(train_data_dir):
            return APIResponseFail(message="训练数据集路径不存在或没有图片，请检查目录。")

        if "prompt_file" in config and str(config["prompt_file"]).strip() != "":
            prompt_file = str(config["prompt_file"]).strip()
            if not os.path.exists(prompt_file):
                return APIResponseFail(message=f"Prompt 文件 {prompt_file} 不存在，请检查路径。")
            config["sample_prompts"] = prompt_file
            train_utils.normalize_sample_prompt_file(prompt_file)
        elif should_generate_sample_prompts(config):
            musubi_apply_sample_defaults(config)
            try:
                positive_prompt, sample_prompts_arg = get_sample_prompts(config=config, model_train_type=model_train_type)
                if positive_prompt is not None and train_utils.is_promopt_like(sample_prompts_arg):
                    sample_prompts_file = os.path.join(ctx.autosave_dir, f"{ctx.timestamp}-promopt.txt")
                    with open(sample_prompts_file, "w", encoding="utf-8", newline="\n") as f:
                        f.write(sample_prompts_arg + "\n")
                    config["sample_prompts"] = sample_prompts_file
                    log.info(f"Wrote prompts to file {sample_prompts_file}")
            except ValueError as e:
                log.error(f"Error while processing prompts: {e}")
                return APIResponseFail(message=str(e))
        else:
            train_utils.strip_disabled_preview_fields(config)

        if config.get("sample_prompts"):
            train_utils.normalize_sample_prompt_file(str(config["sample_prompts"]))
        else:
            config.pop("sample_at_first", None)
            config.pop("sample_every_n_epochs", None)
            config.pop("sample_every_n_steps", None)

        sanitize_config(config)

        run_id = f"{ctx.timestamp}-musubi"
        adapted = adapt_musubi_config(config, runtime, run_id)
        preflight = run_musubi_preflight(adapted.values, runtime, adapted.dataset)
        if not preflight.ok:
            return musubi_fail_from_preflight(preflight)
        toml_file_path = Path(ctx.autosave_dir) / f"{run_id}.toml"
        dataset_file_path = Path(ctx.autosave_dir) / f"{run_id}-dataset.toml"
        dataset_file_path.write_text(dump_musubi_dataset_toml(adapted.dataset), encoding="utf-8")
        adapted.values["dataset_config"] = dataset_file_path.resolve().as_posix()
        toml_file_path.write_text(dump_musubi_train_toml(adapted.values), encoding="utf-8")

        metadata = {
            "output_dir": adapted.values.get("output_dir"),
            "output_name": adapted.values.get("output_name"),
            "logging_dir": adapted.values.get("logging_dir"),
            "warnings": [*adapted.warnings, *preflight.warnings],
        }
        return process.run_musubi_train(
            str(toml_file_path), runtime, adapted.values, ctx.gpu_ids, metadata=metadata
        )
    except MusubiAdapterError as exc:
        return APIResponseFail(message=str(exc))
    except Exception as exc:  # noqa: BLE001 - keep API failures structured
        log.error(f"musubi-tuner launch failed: {exc}")
        return APIResponseFail(message=f"musubi-tuner launch failed: {exc}")

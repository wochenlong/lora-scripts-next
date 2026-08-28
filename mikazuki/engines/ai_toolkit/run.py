"""ai-toolkit /api/run handler (gate -> adapt -> preflight -> dump -> launch)."""

import os

from pathlib import Path

import mikazuki.process as process
from mikazuki.app.models import APIResponseFail
from mikazuki.app.train_submit import (
    _missing_standard_train_field,
    get_sample_prompts,
    sanitize_config,
    should_generate_sample_prompts,
    toml,
)
from mikazuki.log import log
from mikazuki.engines.ai_toolkit.adapter import (
    AdapterError as AiToolkitAdapterError,
    adapt_config as adapt_ai_toolkit_config,
    dump_yaml as dump_ai_toolkit_yaml,
)
from mikazuki.engines.ai_toolkit.environment import audit_environment as audit_ai_toolkit_environment
from mikazuki.engines.ai_toolkit.extension_state import (
    STATE_READY as AI_TOOLKIT_STATE_READY,
    default_layout as ai_toolkit_default_layout,
    read_extension_status as read_ai_toolkit_extension_status,
    write_install_state as write_ai_toolkit_install_state,
)
from mikazuki.engines.ai_toolkit.preflight import run_preflight as run_ai_toolkit_preflight
from mikazuki.engines.ai_toolkit.settings import (
    discover_runtime as discover_ai_toolkit_runtime,
    feature_enabled as ai_toolkit_feature_enabled,
)
from mikazuki.engines.runner import RunContext
from mikazuki.utils import train_utils


def ai_toolkit_runtime():
    return discover_ai_toolkit_runtime(lora_next_root=Path.cwd())


def ai_toolkit_disabled_response():
    return APIResponseFail(
        message="ai-toolkit backend is temporarily disabled by maintainer (LORA_ENABLE_AI_TOOLKIT=0)."
    )


def ai_toolkit_ready_gate():
    layout = ai_toolkit_default_layout(Path.cwd())
    status = read_ai_toolkit_extension_status(layout)
    if status.state != AI_TOOLKIT_STATE_READY:
        return False, APIResponseFail(
            message="ai-toolkit 插件未就绪。请先在「设置 → 训练引擎」安装或修复 ai-toolkit 插件。",
            data=status.as_dict(),
        )
    audit = (status.facts or {}).get("audit", {})
    if not audit.get("ok"):
        return False, APIResponseFail(
            message="ai-toolkit 环境审计未通过。请先修复插件再训练。",
            data=status.as_dict(),
        )
    drift = audit_ai_toolkit_environment(ai_toolkit_runtime())
    if not drift.ok:
        write_ai_toolkit_install_state(layout, "broken", {"audit": drift.as_dict()}, "; ".join(drift.errors))
        return False, APIResponseFail(
            message="ai-toolkit 环境发生漂移。请先修复插件再训练。",
            data=drift.as_dict(),
        )
    return True, None


def ai_toolkit_fail_from_preflight(result):
    errors = list(getattr(result, "errors", None) or [])
    if errors:
        detail = "; ".join(errors[:4])
        if len(errors) > 4:
            detail += f" …（共 {len(errors)} 项）"
        message = f"ai-toolkit 预检查失败：{detail}"
    else:
        message = "ai-toolkit 预检查失败（未返回具体原因）"
    return APIResponseFail(message=message, data=result.as_dict())


def handle_run(config: dict, ctx: RunContext):
    model_train_type = ctx.model_train_type
    variant = ctx.variant or "klein-4b"
    if not ai_toolkit_feature_enabled():
        return ai_toolkit_disabled_response()
    ready, failure = ai_toolkit_ready_gate()
    if not ready:
        return failure
    try:
        runtime = ai_toolkit_runtime()
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
            config.setdefault("sample_width", 1024)
            config.setdefault("sample_height", 1024)
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

        sanitize_config(config)

        run_id = f"{ctx.timestamp}-ai-toolkit"
        adapted = adapt_ai_toolkit_config(config, runtime, run_id, variant)
        preflight = run_ai_toolkit_preflight(adapted.config, runtime, variant, te_path=adapted.te_path)
        if not preflight.ok:
            return ai_toolkit_fail_from_preflight(preflight)
        yaml_file_path = Path(ctx.autosave_dir) / f"{run_id}.yaml"
        yaml_file_path.write_text(dump_ai_toolkit_yaml(adapted.config), encoding="utf-8")
        # UI-dialect TOML alongside the engine YAML so /api/tasks/{id}/config
        # re-import works (it toml-parses config_path and expects UI keys).
        ui_toml_path = Path(ctx.autosave_dir) / f"{run_id}.toml"
        ui_toml_path.write_text(toml.dumps(config), encoding="utf-8")

        metadata = {
            "output_dir": adapted.config["config"]["process"][0]["training_folder"],
            "output_name": adapted.config["config"]["name"],
            "logging_dir": adapted.config["config"]["process"][0]["log_dir"],
            "text_encoder": adapted.te_path,
            "config_path": str(ui_toml_path.resolve()),
            "engine_config_path": str(yaml_file_path.resolve()),
            "warnings": [*adapted.warnings, *preflight.warnings],
        }
        return process.run_ai_toolkit_train(
            str(yaml_file_path), runtime, variant, ctx.gpu_ids, metadata=metadata, te_path=adapted.te_path
        )
    except AiToolkitAdapterError as exc:
        return APIResponseFail(message=str(exc))
    except Exception as exc:  # noqa: BLE001 - keep API failures structured
        log.error(f"ai-toolkit launch failed: {exc}")
        return APIResponseFail(message=f"ai-toolkit launch failed: {exc}")

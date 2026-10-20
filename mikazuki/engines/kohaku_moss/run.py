"""Gate, adapt, preflight, persist and launch KohakuMossTrainer."""
from pathlib import Path
import uuid

import toml

from mikazuki.app.models import APIResponseFail, APIResponseSuccess
from mikazuki.tasks import TaskStatus, tm
from .adapter import adapt_config, dump_config
from .extension_state import check_runtime
from .installer import assert_idle
from .launcher import build_launch_spec
from .manifest import UPSTREAM
from .preflight import check_inputs
from .settings import runtime


def build_dry_run(config, rt):
    try:
        adapted = adapt_config(config, rt)
        preflight = check_inputs(adapted, materialize=False)
        spec = build_launch_spec(rt, "<generated-config>", config.get("gpu_ids"))
        return {
            **preflight,
            "config": adapted.as_dict(),
            "command": spec.command,
            "cwd": str(spec.cwd),
            "source_commit": UPSTREAM["commit"],
            "training_started": False,
        }
    except (ValueError, OSError) as exc:
        return {"ok": False, "errors": [str(exc)], "warnings": [], "facts": {}, "training_started": False}


def handle_run(config, ctx):
    try:
        rt = runtime()
        assert_idle(maintenance_only=True)
        check_runtime(rt)
        adapted = adapt_config(config, rt)
        preflight = check_inputs(adapted, materialize=True)
        if not preflight["ok"]:
            raise ValueError("; ".join(preflight["errors"]))
        run_id = f"{ctx.timestamp}-kohaku-moss-{uuid.uuid4().hex[:8]}"
        engine_config = dump_config(adapted, ctx.autosave_dir, run_id)
        spec = build_launch_spec(rt, engine_config, ctx.gpu_ids)
        ui_config = Path(ctx.autosave_dir) / f"{run_id}.toml"
        ui_config.write_text(
            toml.dumps({**config, "model_train_type": "kohaku-moss-image-lora", **({"gpu_ids": ctx.gpu_ids} if ctx.gpu_ids else {})}),
            encoding="utf-8",
        )
        output_dir = Path(adapted.values["OUTPUT_DIR"]) / adapted.values["RUN_NAME"]
        metadata = {
            "backend": "kohaku-moss",
            "train_type": "kohaku-moss-image-lora",
            "job_label": "MOSS-Image LoRA (KohakuMossTrainer)",
            "config_path": str(ui_config.resolve()),
            "engine_config_path": str(engine_config),
            "output_dir": str(output_dir),
            "output_name": adapted.values["RUN_NAME"],
            "logging_dir": str(output_dir),
            "source_commit": UPSTREAM["commit"],
            "command": spec.command,
            "total_steps": adapted.values["STEPS"],
            "warnings": adapted.warnings,
        }
        task = tm.create_task(spec.command, spec.env, metadata=metadata, cwd=str(spec.cwd))
        queued = task.status == TaskStatus.QUEUED
        tm.submit(task)
        return APIResponseSuccess(data={
            "task_id": task.task_id,
            "queued": queued,
            "metadata": metadata,
            "config_path": str(ui_config.resolve()),
            "train_log_path": "/train-log",
            "train_log_query": f"task_id={task.task_id}",
        })
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc))

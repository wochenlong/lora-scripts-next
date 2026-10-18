"""Registry hook: gate -> adapt -> preflight -> persist -> shared task queue."""
from pathlib import Path
import re
import uuid

import toml

from mikazuki.app.models import APIResponseFail, APIResponseSuccess
from mikazuki.tasks import TaskStatus, tm
from .adapter import adapt_config, dump_config
from .extension_state import check_runtime
from .installer import assert_idle
from .launcher import build_train_spec, pipeline_commands
from .manifest import UPSTREAM
from .preflight import check_inputs
from .resource import request_lock
from .settings import runtime


def check_queued_outputs(adapted):
    output = Path(adapted.train["output"])
    for task in tm.tasks.values():
        if task.status not in {TaskStatus.CREATED, TaskStatus.QUEUED, TaskStatus.RUNNING}:
            continue
        metadata = task.metadata
        if metadata.get("backend") != "moss" or not metadata.get("output_dir"):
            continue
        other = Path(metadata["output_dir"]) / (str(metadata.get("output_name", "")) + ".safetensors")
        same_directory = output.parent.resolve() == other.parent.resolve()
        names = (output.stem.casefold(), other.stem.casefold())
        if same_directory and (names[0] == names[1] or re.fullmatch(re.escape(names[0]) + r"_e\d+", names[1]) or re.fullmatch(re.escape(names[1]) + r"_e\d+", names[0])):
            raise ValueError("output_name is reserved by a queued MOSS task / 输出名称已被队列中的 MOSS 任务占用")


def build_dry_run(config, rt):
    try:
        adapted = adapt_config(config, rt)
        facts = check_inputs(adapted)
        # Validate GPU selection without writing configs or spawning anything.
        build_train_spec(rt, "<autosave-config>", config.get("gpu_ids"))
        return {"ok": True, "errors": [], "warnings": adapted.warnings, "facts": facts,
                "config": adapted.as_dict(), "commands": pipeline_commands(rt, adapted),
                "cwd": str(rt.source), "source_commit": UPSTREAM["commit"], "training_started": False}
    except (ValueError, OSError) as exc:
        return {"ok": False, "errors": [str(exc)], "warnings": [], "facts": {}, "training_started": False}


def handle_run(config, ctx):
    with request_lock:
        rt = runtime()
        try:
            assert_idle(maintenance_only=True)
            check_runtime(rt)
            adapted = adapt_config(config, rt)
            facts = check_inputs(adapted)
            check_queued_outputs(adapted)
            # Validate before creating an autosave file.
            build_train_spec(rt, "<autosave-config>", ctx.gpu_ids)
            run_id = f"{ctx.timestamp}-moss-{uuid.uuid4().hex[:8]}"
            engine_config = dump_config(adapted, ctx.autosave_dir, run_id)
            spec = build_train_spec(rt, engine_config, ctx.gpu_ids)
            ui_config = Path(ctx.autosave_dir) / f"{run_id}.toml"
            ui_config.write_text(toml.dumps({**config, "model_train_type": "moss-image-anima-lora",
                                            **({"gpu_ids": ctx.gpu_ids} if ctx.gpu_ids else {})}), encoding="utf-8")
            output = Path(adapted.train["output"])
            metadata = {
                "backend": "moss", "train_type": "moss-image-anima-lora", "job_label": "MOSS-Image LoRA (anima_lora)",
                "config_path": str(ui_config.resolve()), "engine_config_path": str(engine_config),
                "output_dir": str(output.parent), "output_name": output.stem,
                "logging_dir": str(rt.project_root / "logs" / "moss"),
                "log_file": str(rt.project_root / "logs" / "moss" / f"{run_id}.log"),
                "source_commit": UPSTREAM["commit"], "command": spec.command,
                "pipeline_commands": pipeline_commands(rt, adapted),
                "total_steps": facts["total_steps"], "warnings": adapted.warnings,
            }
            task = tm.create_task(spec.command, spec.env, metadata=metadata, cwd=str(spec.cwd))
            queued = task.status == TaskStatus.QUEUED
            tm.submit(task)
            return APIResponseSuccess(data={
                "task_id": task.task_id, "queued": queued, "metadata": metadata,
                "config_path": str(ui_config.resolve()), "train_log_path": "/train-log",
                "train_log_query": f"task_id={task.task_id}", "train_log_stream": f"/api/train/log/stream/{task.task_id}",
            })
        except (ValueError, OSError) as exc:
            return APIResponseFail(message=str(exc))

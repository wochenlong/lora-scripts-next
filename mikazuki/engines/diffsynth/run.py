import uuid
import math
from .resource import request_lock
from .installer import assert_idle
from pathlib import Path
import toml

from mikazuki.app.models import APIResponseSuccess, APIResponseFail
from mikazuki.tasks import tm, TaskStatus
from . import TRAIN_TYPE
from .settings import runtime
from .adapter import adapt_config, dump_config
from .preflight import check_runtime
from .launcher import build_train_spec


def handle_run(config, ctx):
    with request_lock:
        return _handle_run(config, ctx)


def _handle_run(config, ctx):
    rt = runtime()
    try:
        assert_idle(maintenance_only=True)
        check_runtime(rt)
        adapted = adapt_config(config, rt)
        run_id = f"{ctx.timestamp}-diffsynth-{uuid.uuid4().hex[:8]}"
        adapted.output_path = adapted.output_path / run_id
        adapted.arguments["output_path"] = str(adapted.output_path)
        engine_config = dump_config(adapted, ctx.autosave_dir, run_id)
        spec = build_train_spec(rt, engine_config, ctx.gpu_ids)
        ui_config = Path(ctx.autosave_dir) / f"{run_id}.toml"
        ui_config.write_text(toml.dumps({**config, **({"gpu_ids": ctx.gpu_ids} if ctx.gpu_ids else {}), "model_train_type": TRAIN_TYPE}), encoding="utf-8")
        metadata = {
            "backend": "diffsynth", "train_type": TRAIN_TYPE,
            "job_label": "DiffSynth Qwen-Image-2.1 LoRA",
            "config_path": str(ui_config.resolve()), "engine_config_path": str(engine_config.resolve()),
            "output_dir": str(adapted.output_path), "output_name": config["output_name"],
            "logging_dir": str(adapted.output_path / "tensorboard_log"),
            "command": spec.command,
            "total_steps": adapted.engine['lr_schedule']['total_steps'],
            "bucket_summary": adapted.engine.get('bucket_summary', []),
            "warnings": ["保存的检查点为 LoRA 权重，不含优化器状态。"],
        }
        task = tm.create_task(spec.command, spec.env, metadata=metadata, cwd=str(spec.cwd))
        queued = task.status == TaskStatus.QUEUED
        tm.submit(task)
        return APIResponseSuccess(data={"task_id": task.task_id, "queued": queued, "metadata": metadata, "config_path": str(ui_config.resolve()), "train_log_path": "/train-log", "train_log_query": f"task_id={task.task_id}", "train_log_stream": f"/api/train/log/stream/{task.task_id}"})
    except (ValueError, OSError) as exc:
        return APIResponseFail(message=str(exc))

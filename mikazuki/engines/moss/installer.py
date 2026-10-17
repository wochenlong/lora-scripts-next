"""Task-owned MOSS installation/repair using the shared maintenance lane."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import threading
import uuid

from mikazuki.download_sources import DownloadSources, apply_github_prefix
from mikazuki.tasks import LANE_MAINTENANCE, TaskStatus, tm
from .environment import install_commands, process_env
from .extension_state import write_state
from .manifest import UPSTREAM
from .resource import environment_lock, request_lock


def assert_idle(maintenance_only=False):
    if any(
        task.metadata.get("backend") == "moss"
        and (not maintenance_only or task.metadata.get("kind") == "moss_install")
        and task.status in {TaskStatus.CREATED, TaskStatus.QUEUED, TaskStatus.RUNNING}
        for task in tm.tasks.values()
    ):
        raise ValueError("MOSS 任务尚未结束，请先停止任务。")


def source_clone_commands(runtime, sources):
    return [
        ["git", "clone", "--config", "core.autocrlf=false", "--config", "core.eol=lf", "--no-checkout", "--branch", UPSTREAM["branch"], apply_github_prefix(UPSTREAM["github"], sources.github_url_prefix), str(runtime.source)],
        ["git", "-C", str(runtime.source), "checkout", "--detach", UPSTREAM["commit"]],
    ]


def installation_plan(runtime, sources=None):
    sources = sources or DownloadSources()
    return [*source_clone_commands(runtime, sources),
            [sys.executable, "-m", "mikazuki.engines.moss.source_integrity", "--apply", str(runtime.source)],
            *install_commands(runtime, sources)]


def start_install(runtime, sources=None, repair=False):
    sources = sources or DownloadSources()
    commands = installation_plan(runtime, sources)
    with request_lock:
        assert_idle()
        # Detect a worker in another server before registering a new task.
        with environment_lock(runtime.root):
            task_id = f"moss-install-{uuid.uuid4()}"
            plan = {"commands": commands, "repair": repair, "download_sources": sources.as_dict()}
            plan_path = runtime.project_root / "config/autosave" / f"{task_id}.json"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            task = tm.create_task(
                [sys.executable, str(Path(__file__).with_name("install_worker.py")), str(runtime.project_root), str(plan_path), task_id],
                process_env(),
                metadata={"backend": "moss", "kind": "moss_install", "job_label": "修复 MOSS" if repair else "安装 MOSS", "source_commit": UPSTREAM["commit"], "environment_path": str(runtime.root)},
                cwd=str(runtime.project_root), task_id=task_id, lane=LANE_MAINTENANCE,
            )
            facts = {"task_id": task_id, "repair": repair, "source_commit": UPSTREAM["commit"]}
            write_state(runtime, "installing", facts)
        # Release the file lock before spawning the worker that will acquire it.
        try:
            task.execute()
            threading.Thread(target=task.wait, daemon=True).start()
        except Exception as exc:
            write_state(runtime, "broken", facts, str(exc))
            raise
    return {
        "task_id": task_id,
        "log_stream": f"/api/engines/moss/install/log/stream/{task_id}",
        "progress_stream": f"/api/engines/moss/install/progress/stream/{task_id}",
    }


def remove_extension(runtime):
    with request_lock:
        assert_idle()
        with environment_lock(runtime.root):
            if runtime.root.exists():
                shutil.rmtree(runtime.root)

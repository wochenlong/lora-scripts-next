"""Task-owned KohakuMossTrainer installation."""
from __future__ import annotations

import json
import shutil
import sys
import threading
import uuid
from dataclasses import asdict
from pathlib import Path

from mikazuki.download_sources import DownloadSources, apply_github_prefix
from mikazuki.tasks import LANE_MAINTENANCE, TaskStatus, tm

from .environment import install_commands, process_env
from .extension_state import write_state
from .manifest import UPSTREAM
from .resource import environment_lock, request_lock


def assert_idle(maintenance_only=False):
    if any(
        task.metadata.get("backend") == "kohaku-moss"
        and (not maintenance_only or task.metadata.get("kind") == "kohaku_moss_install")
        and task.status in {TaskStatus.CREATED, TaskStatus.QUEUED, TaskStatus.RUNNING}
        for task in tm.tasks.values()
    ):
        raise ValueError("KohakuMossTrainer 任务尚未结束。")


def source_clone_commands(runtime, sources):
    return [
        [
            "git", "clone", "--no-checkout", "--filter=blob:none",
            apply_github_prefix(UPSTREAM["github"], sources.github_url_prefix), str(runtime.source),
        ],
        ["git", "-C", str(runtime.source), "checkout", "--detach", UPSTREAM["commit"]],
    ]


def installation_plan(runtime, sources=None):
    sources = sources or DownloadSources()
    patch = [sys.executable, str(Path(__file__).with_name("patch_upstream.py")), str(runtime.source)]
    return [*source_clone_commands(runtime, sources), patch, *install_commands(runtime, sources)]


def start_install(runtime, sources=None, repair=False):
    sources = sources or DownloadSources()
    with request_lock:
        assert_idle()
        task_id = f"kohaku-moss-install-{uuid.uuid4()}"
        plan_path = runtime.project_root / "config" / "autosave" / f"{task_id}.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            json.dumps({"commands": installation_plan(runtime, sources), "repair": repair, "download_sources": asdict(sources)}),
            encoding="utf-8",
        )
        task = tm.create_task(
            [sys.executable, str(Path(__file__).with_name("install_worker.py")), str(runtime.project_root), str(plan_path), task_id],
            process_env(),
            metadata={"backend": "kohaku-moss", "kind": "kohaku_moss_install", "job_label": "安装 KohakuMossTrainer"},
            task_id=task_id,
            cwd=str(runtime.project_root),
            lane=LANE_MAINTENANCE,
        )
        write_state(runtime, "installing", {"task_id": task_id, "source_commit": UPSTREAM["commit"]})
        task.execute()
        threading.Thread(target=task.wait, daemon=True).start()
    return {
        "task_id": task_id,
        "log_stream": f"/api/engines/kohaku-moss/install/log/stream/{task_id}",
        "progress_stream": f"/api/engines/kohaku-moss/install/progress/stream/{task_id}",
    }


def remove_extension(runtime):
    with request_lock:
        assert_idle()
        with environment_lock(runtime.root):
            if runtime.root.exists():
                shutil.rmtree(runtime.root)

"""Install the complete pinned upstream checkout, leaving training code unchanged."""
import json
import shutil
import threading
import uuid

from mikazuki.download_sources import DownloadSources, apply_github_prefix
from mikazuki.tasks import tm, LANE_MAINTENANCE, TaskStatus
from .environment import install_commands, process_env
from .extension_state import write_state
from .manifest import UPSTREAM


def assert_idle(maintenance_only=False):
    if any((not maintenance_only or t.metadata.get("kind") == "diffsynth_install") and t.metadata.get("backend") == "diffsynth" and t.status in {TaskStatus.CREATED, TaskStatus.QUEUED, TaskStatus.RUNNING} for t in tm.tasks.values()):
        raise ValueError("DiffSynth 任务尚未结束，请先停止任务。")


def installation_plan(runtime, sources):
    return [
        ["git", "clone", "--no-checkout", apply_github_prefix(UPSTREAM["github"], sources.github_url_prefix), str(runtime.source)],
        ["git", "-C", str(runtime.source), "checkout", "--detach", UPSTREAM["commit"]],
        *install_commands(runtime, sources),
    ]


def start_install(runtime, sources=None, repair=False):
    import sys
    from pathlib import Path
    from .resource import request_lock
    with request_lock:
        assert_idle()
        sources = sources or DownloadSources()
        task_id = f"diffsynth-install-{uuid.uuid4()}"
        plan_path = runtime.project_root / "config" / "autosave" / f"{task_id}.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps({"commands": installation_plan(runtime, sources), "repair": repair}), encoding="utf-8")
        command = [sys.executable, str(Path(__file__).with_name("install_worker.py")), str(runtime.project_root), str(plan_path), task_id]
        task = tm.create_task(command, process_env(), metadata={"backend": "diffsynth", "kind": "diffsynth_install", "job_label": "安装 DiffSynth"}, task_id=task_id, lane=LANE_MAINTENANCE)
        write_state(runtime, "installing", {"task_id": task_id})
        # The existing Task owns one supervisor and its entire subprocess tree.
        task.execute()
        threading.Thread(target=task.wait, daemon=True).start()
    return {"task_id": task_id, "log_stream": f"/api/engines/diffsynth/install/log/stream/{task_id}", "progress_stream": f"/api/engines/diffsynth/install/progress/stream/{task_id}"}


def remove_extension(runtime):
    from .resource import request_lock, environment_lock
    with request_lock:
        assert_idle()
        with environment_lock(runtime.root):
            if runtime.root.exists():
                shutil.rmtree(runtime.root)

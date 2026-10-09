"""Install the independent kohya venv; training source stays in the repository."""
import json
import shutil
import threading
import uuid

from mikazuki.download_sources import DownloadSources
from mikazuki.tasks import tm, LANE_MAINTENANCE, TaskStatus
from .environment import install_commands, process_env
from .extension_state import write_state


def assert_idle(maintenance_only=False):
    for task in tm.tasks.values():
        if task.status not in {TaskStatus.CREATED, TaskStatus.QUEUED, TaskStatus.RUNNING}:
            continue
        if task.metadata.get("kind") == "kohya_install":
            raise ValueError("kohya 环境任务尚未结束，请先停止任务。")
        # kohya training tasks carry the historical "standard" backend.
        if not maintenance_only and task.metadata.get("backend") == "standard":
            raise ValueError("kohya 训练任务尚未结束，请先停止任务。")


def installation_plan(runtime, sources):
    return install_commands(runtime, sources)


def start_install(runtime, sources=None, repair=False):
    import sys
    from pathlib import Path
    from .resource import request_lock
    with request_lock:
        assert_idle()
        sources = sources or DownloadSources()
        task_id = f"kohya-install-{uuid.uuid4()}"
        plan_path = runtime.project_root / "config" / "autosave" / f"{task_id}.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps({"commands": installation_plan(runtime, sources), "repair": repair}), encoding="utf-8")
        command = [sys.executable, str(Path(__file__).with_name("install_worker.py")), str(runtime.project_root), str(plan_path), task_id]
        task = tm.create_task(command, process_env(), metadata={"backend": "kohya", "kind": "kohya_install", "job_label": "安装 kohya (sd-scripts)"}, task_id=task_id, lane=LANE_MAINTENANCE)
        write_state(runtime, "installing", {"task_id": task_id})
        # The existing Task owns one supervisor and its entire subprocess tree.
        task.execute()
        threading.Thread(target=task.wait, daemon=True).start()
    return {"task_id": task_id, "log_stream": f"/api/engines/kohya/install/log/stream/{task_id}", "progress_stream": f"/api/engines/kohya/install/progress/stream/{task_id}"}


def remove_extension(runtime):
    from .resource import request_lock, environment_lock
    with request_lock:
        assert_idle()
        with environment_lock(runtime.root):
            if runtime.root.exists():
                shutil.rmtree(runtime.root)

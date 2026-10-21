"""Persistent install state for the optional runtime."""
import json

from .settings import PYTHON_VERSION, TRAIN_SCRIPT, feature_enabled


def write_state(runtime, state, facts=None, reason=""):
    runtime.root.mkdir(parents=True, exist_ok=True)
    temporary = runtime.state_file.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"state": state, "facts": facts or {}, "reason": reason}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(runtime.state_file)


def repair_runtime_venv(runtime, log=None):
    """Repair a packaged KohakuMoss venv after its project root moves."""
    from mikazuki.engines.portable_venv import repair_venv_base

    return repair_venv_base(runtime.python, runtime.python_install_dir, PYTHON_VERSION, log=log)


def read_status(runtime):
    if runtime.state_file.is_file():
        try:
            data = json.loads(runtime.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {"state": "broken", "facts": {}, "reason": "安装状态文件损坏。"}
    elif runtime.root.exists():
        data = {"state": "installed_unverified", "facts": {}, "reason": "检测到运行时但尚未审计。"}
    else:
        data = {"state": "not_installed", "facts": {}, "reason": ""}
    if data["state"] in {"installing", "auditing"}:
        from mikazuki.tasks import TaskStatus, tm
        task = tm.tasks.get(data.get("facts", {}).get("task_id"))
        if task is None or task.status in {TaskStatus.FAILED, TaskStatus.TERMINATED, TaskStatus.FINISHED}:
            data.update(state="broken", reason="安装任务已中断；请重新安装或修复环境。")
    complete = runtime.python.is_file() and runtime.kogine.is_file() and (runtime.source / TRAIN_SCRIPT).is_file()
    repair = repair_runtime_venv(runtime) if runtime.python.is_file() else "ok"
    if repair == "broken":
        data.update(
            state="broken",
            reason=f"独立环境引用的基础 Python 已失效，且 .python 下没有 Python {PYTHON_VERSION}；请修复整合包运行时。",
        )
    if data["state"] == "ready" and not complete:
        data.update(state="broken", reason="独立 Python、kogine 或训练入口缺失。")
    data["feature_enabled"] = feature_enabled()
    if not data["feature_enabled"]:
        data["state"] = "disabled"
    data["runtime"] = {
        "python": str(runtime.python),
        "environment_path": str(runtime.root),
        "source": str(runtime.source),
    }
    return data


def check_runtime(runtime):
    status = read_status(runtime)
    if status["state"] != "ready":
        raise ValueError(f"KohakuMossTrainer 未就绪：{status.get('reason') or status['state']}")

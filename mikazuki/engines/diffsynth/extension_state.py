import json
import hashlib
import subprocess

from .settings import TRAIN_SCRIPT, feature_enabled


def write_state(runtime, state, facts=None, reason=""):
    runtime.root.mkdir(parents=True, exist_ok=True)
    temporary = runtime.state_file.with_suffix(".tmp")
    temporary.write_text(json.dumps({"state": state, "facts": facts or {}, "reason": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(runtime.state_file)


def fingerprint(runtime):
    files = [runtime.python, runtime.source / TRAIN_SCRIPT, runtime.source / "pyproject.toml"]
    files += sorted(runtime.source.glob("diffsynth/**/*.py"))
    files += sorted((runtime.root / ".venv").glob("**/*.dist-info/METADATA"))
    stats = [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in files if p.is_file()]
    head = subprocess.run(["git", "-C", str(runtime.source), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return hashlib.sha256(json.dumps([head, stats]).encode()).hexdigest()


def read_status(runtime):
    data = json.loads(runtime.state_file.read_text(encoding="utf-8")) if runtime.state_file.exists() else {"state": "not_installed", "facts": {}}
    if data["state"] in {"installing", "auditing"}:
        from mikazuki.tasks import tm, TaskStatus
        task = tm.tasks.get(data["facts"].get("task_id"))
        if task is None or task.status in {TaskStatus.FAILED, TaskStatus.TERMINATED, TaskStatus.FINISHED}:
            data.update(state="broken", reason="安装中断，请修复 DiffSynth 环境。")
    if data["state"] == "ready" and not (runtime.python.is_file() and (runtime.source / TRAIN_SCRIPT).is_file()):
        data.update(state="broken", reason="训练入口或独立 Python 缺失，请修复环境。")
    if data["state"] == "ready" and data["facts"].get("fingerprint") != fingerprint(runtime):
        data.update(state="broken", reason="环境或源码已变化，请修复后重新检查。")
    data["feature_enabled"] = feature_enabled()
    if not data["feature_enabled"]:
        data["state"] = "disabled"
    data["runtime"] = {"python": str(runtime.python), "environment_path": str(runtime.root), "source": str(runtime.source)}
    return data

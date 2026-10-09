import json
import hashlib

from .environment import TRAINING_DEPS, TORCH_PINS, TORCH_PINS_AARCH64


def write_state(runtime, state, facts=None, reason=""):
    runtime.root.mkdir(parents=True, exist_ok=True)
    temporary = runtime.state_file.with_suffix(".tmp")
    temporary.write_text(json.dumps({"state": state, "facts": facts or {}, "reason": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(runtime.state_file)


def fingerprint(runtime):
    # The training source ships with the repository and updates via git pull;
    # only the venv content and the pinned dependency set gate readiness.
    files = [runtime.python]
    files += sorted((runtime.root / ".venv").glob("**/*.dist-info/METADATA"))
    stats = []
    for path in files:
        if not path.is_file():
            continue
        try:
            identity = path.relative_to(runtime.root).as_posix()
        except ValueError:
            identity = path.name
        stats.append((identity, path.stat().st_size, path.stat().st_mtime_ns))
    pins = [*TRAINING_DEPS, *TORCH_PINS, *TORCH_PINS_AARCH64]
    return hashlib.sha256(json.dumps([pins, stats]).encode()).hexdigest()


def read_status(runtime):
    data = json.loads(runtime.state_file.read_text(encoding="utf-8")) if runtime.state_file.exists() else {"state": "not_installed", "facts": {}}
    if data["state"] in {"installing", "auditing"}:
        from mikazuki.tasks import tm, TaskStatus
        task = tm.tasks.get(data["facts"].get("task_id"))
        if task is None or task.status in {TaskStatus.FAILED, TaskStatus.TERMINATED, TaskStatus.FINISHED}:
            data.update(state="broken", reason="安装中断，请修复 kohya 环境。")
    if data["state"] == "ready" and not runtime.python.is_file():
        data.update(state="broken", reason="独立 Python 缺失，请修复环境。")
    if data["state"] == "ready" and data["facts"].get("fingerprint") != fingerprint(runtime):
        data.update(state="broken", reason="环境已变化，请修复后重新检查。")
    data["feature_enabled"] = True
    data["runtime"] = {"python": str(runtime.python), "environment_path": str(runtime.root)}
    return data

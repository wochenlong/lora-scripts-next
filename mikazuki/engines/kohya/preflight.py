from .extension_state import read_status, audit_main_env_python
from .environment import audit_python


def check_runtime(runtime):
    status = read_status(runtime)
    if status["state"] != "ready":
        raise ValueError("kohya (sd-scripts) 环境未就绪，请到训练引擎管理中安装或修复。")
    # Explicit preflight always re-audits the selected interpreter live; the
    # status-poll audit cache may be stale by the time a run is submitted.
    if status["facts"].get("mode") == "main_env":
        audit = audit_main_env_python(status["runtime"]["python"])
    else:
        audit = audit_python(status["runtime"]["python"])
    if not audit["ok"]:
        raise ValueError("kohya 环境检查失败: " + "; ".join(audit["errors"]))

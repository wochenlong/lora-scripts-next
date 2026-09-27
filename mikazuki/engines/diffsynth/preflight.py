from .extension_state import read_status
from .environment import audit_environment


def check_runtime(runtime):
    status = read_status(runtime)
    if status["state"] != "ready":
        raise ValueError("DiffSynth 环境未就绪，请到训练引擎管理中安装或修复。")
    audit = audit_environment(runtime)
    if not audit["ok"]:
        raise ValueError("DiffSynth 环境检查失败: " + "; ".join(audit["errors"]))

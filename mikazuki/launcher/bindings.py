"""已有训练适配器的 opt-in 绑定桥；桌面托管时绝不猜测旧环境或 GUI Python。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .runtime import ControlError, RuntimeLayout


CONTEXT_ENV = "NEXT_TRAINER_LAUNCHER_CONTEXT"


def context_optional():
    raw = os.environ.get(CONTEXT_ENV, "")
    if not raw:
        return None
    if len(raw) > 128 * 1024:
        raise ControlError("launcher_context_size", "启动器上下文超过上限")
    value = json.loads(raw)
    if value.get("schema_version") != 1:
        raise ControlError("launcher_context_version", "启动器上下文版本不支持")
    return value


def managed_request(engine_id):
    context = context_optional()
    if context is None:
        return None
    return {"schema_version": 1, "root": context["root"], "release_id": context["release_id"], "profile_id": context.get("profile_id", "default"), "engine_id": engine_id}


def active_layout(engine_id):
    from .control import _state, _receipt
    request = managed_request(engine_id)
    if request is None:
        return None
    layout = RuntimeLayout(Path(request["root"]), request["release_id"], engine_id, profile_id=request["profile_id"])
    state = _state(layout)
    if not state or state.get("dirty") or state.get("pending") or state.get("status") != "ready" or state.get("validated_generation") != state.get("generation"):
        raise ValueError(f"{engine_id} 的桌面受管实例未就绪，请使用启动器检查与修复")
    layout = RuntimeLayout(layout.root, layout.release_id, engine_id, state["instance_id"], request["profile_id"])
    _receipt(layout, state)
    context = context_optional()
    fixed = context.get("engine_catalog", {}).get(engine_id)
    if not fixed or fixed["sha256"] != state["lock_sha256"]:
        raise ValueError(f"{engine_id} 已安装实例与当前发布资产锁不一致，请显式重建")
    return layout


def managed_status(engine_id):
    from .control import inspect_readonly
    request = managed_request(engine_id)
    if request is None:
        return None
    report = inspect_readonly(request)
    state = report.get("state", {})
    layout = RuntimeLayout(Path(request["root"]), request["release_id"], engine_id, state.get("instance_id", ""), request["profile_id"])
    return {"state": "ready" if report["installation"] == "ready" else "not_installed" if report["installation"] == "missing" else "broken", "reason": "; ".join(item.get("message", item.get("path", "")) for item in report["issues"]), "facts": {"mode": "standalone", "launcher": report}, "feature_enabled": True, "runtime": {"python": str(layout.python) if layout.instance_id else "", "environment_path": str(layout.environment_root) if layout.instance_id else "", "source": str(layout.engine_source_root)}}


def training_gate(engine_id):
    """GUI 运行 lease 已保护实例；原训练 preflight 继续负责主动导入/CUDA。"""
    request = managed_request(engine_id)
    if request is None:
        return None
    active_layout(engine_id)
    result = managed_status(engine_id)
    if result["state"] != "ready":
        raise ValueError(f"{engine_id} 受管实例文件校验未通过：{result['reason']}")
    return result


def reject_legacy_mutation():
    if context_optional() is not None:
        raise ValueError("桌面受管环境请使用启动器安装/精准修复接口；旧安装器不可修改正式实例")

"""已有训练适配器的 opt-in 绑定桥；桌面托管时绝不猜测旧环境或 GUI Python。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from contextlib import contextmanager

from .runtime import ControlError, RuntimeLayout, engine_lease


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
    """校验受管实例；调用方的目标引擎 lease 保护预检和进程生命周期。"""
    request = managed_request(engine_id)
    if request is None:
        return None
    active_layout(engine_id)
    result = managed_status(engine_id)
    if result["state"] != "ready":
        raise ValueError(f"{engine_id} 受管实例文件校验未通过：{result['reason']}")
    return result


_TASK_ENGINES = {"standard": "kohya", "kohya": "kohya", "anima-lora-fast": "anima-fast",
                 "anima-fast": "anima-fast", "ai-toolkit": "ai-toolkit", "diffsynth": "diffsynth"}


def _training_snapshot(engine_id):
    from .control import _state
    layout = active_layout(engine_id)
    if layout is None:
        return None
    state = _state(layout)
    return {"root": str(layout.root), "release_id": layout.release_id, "engine_id": engine_id,
            "instance_id": state["instance_id"], "generation": state["generation"]}


def bind_training_task(metadata):
    """只保存稳定绑定，不持有排队期锁；重试仍保留原命令的绑定身份。"""
    engine_id = _TASK_ENGINES.get(metadata.get("backend"))
    request = managed_request(engine_id) if engine_id else None
    if request is None or "launcher_binding" in metadata:
        return
    layout = RuntimeLayout(Path(request["root"]), request["release_id"], engine_id, profile_id=request["profile_id"])
    with engine_lease(layout, mode="training"):
        metadata["launcher_binding"] = _training_snapshot(engine_id)


@contextmanager
def managed_training_lease(metadata):
    """启动前原子取得使用权，再核对排队命令对应的环境实例和代次。"""
    engine_id = _TASK_ENGINES.get(metadata.get("backend"))
    request = managed_request(engine_id) if engine_id else None
    if request is None:
        yield
        return
    layout = RuntimeLayout(Path(request["root"]), request["release_id"], engine_id, profile_id=request["profile_id"])
    with engine_lease(layout, mode="training"):
        expected = metadata.get("launcher_binding")
        if expected is None or expected != _training_snapshot(engine_id):
            raise ControlError("training_binding_changed", f"{engine_id} 的环境绑定已变化，请重新提交训练任务")
        yield layout


@contextmanager
def managed_preflight_lease(engine_id):
    """主动导入/预检使用同一目标锁；网页本身不占用任何训练引擎。"""
    if engine_id not in set(_TASK_ENGINES.values()):
        yield
        return
    request = managed_request(engine_id)
    if request is None:
        yield
        return
    layout = RuntimeLayout(Path(request["root"]), request["release_id"], engine_id, profile_id=request["profile_id"])
    with engine_lease(layout, mode="training"):
        yield


def reject_legacy_mutation():
    if context_optional() is not None:
        raise ValueError("桌面受管环境请使用启动器安装/精准修复接口；旧安装器不可修改正式实例")

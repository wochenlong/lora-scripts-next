"""网页适配器：与桌面共享 dispatch，客户端不能选择目录或资产信任根。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time

from .control import dispatch
from .recipes import ENGINES
from .runtime import ControlError, RuntimeLayout, guard, sha_file


CONTEXT_ENV = "NEXT_TRAINER_LAUNCHER_CONTEXT"


def environment_context() -> dict:
    """仅父启动器进程注入；不从 HTTP 参数、训练配置或磁盘待修树取信任根。"""
    raw = os.environ.get(CONTEXT_ENV, "")
    if not raw or len(raw) > 128 * 1024:
        raise ControlError("launcher_context_missing", "此 GUI 未由正式桌面启动器托管")
    context = json.loads(raw)
    if context.get("schema_version") != 1:
        raise ControlError("launcher_context_version", "启动器上下文版本不支持")
    RuntimeLayout(Path(context["root"]), context["release_id"], "kohya", profile_id=context.get("profile_id", "default"))
    return context


class EngineAdapter:
    def __init__(self, context_provider=environment_context, allow_mutations=False):
        self.context_provider = context_provider
        self.allow_mutations = allow_mutations
        self.plans = {}
        self.mutex = threading.Lock()

    def request(self, engine_id, action, needs_lock=False):
        if engine_id not in ENGINES:
            raise ControlError("unsupported_engine", "该引擎没有启动器适配器")
        context = self.context_provider()
        request = {"schema_version": 1, "root": context["root"], "release_id": context["release_id"], "profile_id": context.get("profile_id", "default"), "engine_id": engine_id, "action": action}
        if needs_lock:
            fixed = context.get("engine_catalog", {}).get(engine_id)
            if not fixed:
                raise ControlError("publisher_catalog_missing", "当前发布包缺少该引擎的资产锁；请更新正式启动器目录")
            lock_path = guard(Path(fixed["lock_path"]), Path(context["root"]))
            if sha_file(lock_path) != fixed["sha256"]:
                raise ControlError("publisher_catalog_changed", "随包引擎资产锁摘要不符")
            request.update(lock_path=str(lock_path), lock_sha256=fixed["sha256"])
        return request

    def inspect(self, engine_id):
        return dispatch(self.request(engine_id, "inspect_readonly"))

    def plan(self, engine_id, installing=False, rebuild=False):
        request = self.request(engine_id, "plan_install" if installing else "plan_repair", True)
        request["rebuild"] = bool(rebuild)
        result = dispatch(request)
        key = result["plan_sha256"]
        with self.mutex:
            now = time.monotonic()
            self.plans = {k: v for k, v in self.plans.items() if now - v[0] < 1800}
            if len(self.plans) >= 64:
                self.plans.pop(next(iter(self.plans)))
            self.plans[key] = (now, request, result)
        return result

    def apply(self, engine_id, plan_sha256):
        self.require_desktop_action()
        with self.mutex:
            stored = self.plans.get(plan_sha256)
        if not stored or time.monotonic() - stored[0] > 1800:
            raise ControlError("plan_expired", "计划不存在或已过期，请重新检查")
        _, initial_request, planned = stored
        current = self.request(engine_id, "repair_apply", True)
        if any(current.get(name) != initial_request.get(name) for name in ("root", "release_id", "profile_id", "engine_id", "lock_path", "lock_sha256")):
            raise ControlError("context_changed", "启动器绑定已变化，请重新生成计划")
        # 下载由桌面的受控下载器执行；网页无法覆盖下载来源和写入目录。
        if planned["missing_assets"]:
            raise ControlError("desktop_download_required", "计划需要下载固定资产，请在桌面启动器完成资产准备后重新检查")
        result = dispatch({**current, "plan": planned, "plan_sha256": plan_sha256})
        with self.mutex:
            self.plans.pop(plan_sha256, None)
        return result

    def probe(self, engine_id, scope="imports"):
        self.require_desktop_action()
        if scope not in {"metadata", "imports", "cuda"}:
            raise ControlError("unsupported_probe", "探测范围不支持")
        return dispatch({**self.request(engine_id, "probe_execute"), "probe_scope": scope})

    def recover(self, engine_id):
        self.require_desktop_action()
        return dispatch(self.request(engine_id, "recover"))

    def require_desktop_action(self):
        if not self.allow_mutations:
            raise ControlError("desktop_action_required", "GUI 运行期间持有受管工作区 lease；请停止 GUI 后在桌面启动器执行探测、修复或恢复")


def create_router(context_provider=environment_context, *, allow_mutations=False):
    # 仅网页加载这一层时需要 FastAPI；worker 始终只依赖标准库。
    from fastapi import APIRouter, Body, HTTPException
    from starlette.concurrency import run_in_threadpool

    router = APIRouter(prefix="/launcher/engines", tags=["launcher engines"])
    adapter = EngineAdapter(context_provider, allow_mutations=allow_mutations)

    async def execute(call, *args):
        try:
            return await run_in_threadpool(call, *args)
        except ControlError as error:
            raise HTTPException(status_code=409, detail={"code": error.code, "message": str(error)}) from error

    @router.get("/{engine_id}/inspect")
    async def inspect(engine_id: str):
        return await execute(adapter.inspect, engine_id)

    @router.post("/{engine_id}/plan")
    async def plan(engine_id: str, body: dict = Body(default={})):
        if set(body) - {"install", "rebuild"} or any(not isinstance(value, bool) for value in body.values()):
            raise HTTPException(status_code=422, detail="只接受 install/rebuild 布尔参数")
        return await execute(adapter.plan, engine_id, body.get("install", False), body.get("rebuild", False))

    @router.post("/{engine_id}/apply")
    async def apply(engine_id: str, body: dict = Body(...)):
        if set(body) != {"plan_sha256"} or not isinstance(body["plan_sha256"], str):
            raise HTTPException(status_code=422, detail="只接受此前由服务器生成的 plan_sha256")
        return await execute(adapter.apply, engine_id, body["plan_sha256"])

    @router.post("/{engine_id}/probe")
    async def probe(engine_id: str, body: dict = Body(default={})):
        if set(body) - {"scope"}:
            raise HTTPException(status_code=422, detail="只接受 scope 参数")
        return await execute(adapter.probe, engine_id, body.get("scope", "imports"))

    @router.post("/{engine_id}/recover")
    async def recover(engine_id: str):
        return await execute(adapter.recover, engine_id)

    return router

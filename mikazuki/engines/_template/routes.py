"""Engine routes — 挂载在 /api/engines/<id>/* 的处理器。

职责：实现引擎生命周期路由。通用路由器按名字拾取下列函数，缺省行为：
status 必须实现；install/repair/uninstall 缺失时返回「内置引擎」错误；
preflight/dry_run 缺失时 404。

签名约定（鸭子类型，框架不做强制）：
- ``async def status()`` → APIResponseSuccess(data={state, feature_enabled, runtime...})
- ``async def preflight(config: dict)``
- ``async def dry_run(config: dict)``
- ``async def install(payload: dict, force_install: bool = False)``
- ``async def repair(payload: dict)``  → 通常 ``install(payload, force_install=True)``
- ``async def uninstall()``
完成判据：GET /api/engines/<id>/status 返回 200 且 state 语义正确；
安装流能返回 task_id + log_stream/progress_stream。
参考实现：mikazuki/engines/anima_fast/routes.py、musubi/routes.py。
"""

from mikazuki.app.models import APIResponseSuccess


async def status():
    return APIResponseSuccess(data={"state": "not_installed", "feature_enabled": True})

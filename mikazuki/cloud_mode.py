"""云端单引擎镜像模式（start_cloud.sh 装机后启动时注入环境变量）。

只有经 start_cloud 启动的实例才是 cloud 模式；其他入口启动概不负责。
cloud 模式下引擎的安装/修复/卸载被禁用：镜像装机时已把锁定引擎 slim 进
宿主环境，再装新引擎（isolated venv）会吃掉云盘空间，卸载则会让
.cloud_install_done 指纹与实例状态漂移。
"""
from __future__ import annotations

import os

ENV_CLOUD = "NEXT_TRAINER_CLOUD"
ENV_CLOUD_ENGINE = "NEXT_TRAINER_CLOUD_ENGINE"


def current(env: dict | None = None) -> dict:
    env = env if env is not None else os.environ
    active = str(env.get(ENV_CLOUD, "")).strip() == "1"
    engine = str(env.get(ENV_CLOUD_ENGINE, "")).strip() or None
    return {"cloud_mode": active, "engine": engine if active else None}


def install_block_reason(engine_id: str, env: dict | None = None) -> str | None:
    info = current(env)
    if not info["cloud_mode"]:
        return None
    locked = info["engine"] or "(未知)"
    if engine_id != info["engine"]:
        return f"当前为云端单引擎镜像（锁定引擎 {locked}），不支持安装/修复 {engine_id}。"
    return None


def uninstall_block_reason(engine_id: str, env: dict | None = None) -> str | None:
    info = current(env)
    if not info["cloud_mode"]:
        return None
    return "云端单引擎镜像不支持卸载引擎；如需更换引擎请使用对应镜像。"

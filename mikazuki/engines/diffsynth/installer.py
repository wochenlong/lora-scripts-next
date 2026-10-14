"""Install and surgical repair for the DiffSynth extension (#462)."""
from __future__ import annotations

import json
import shutil
import threading
import uuid
from pathlib import Path

from mikazuki.download_sources import DownloadSources, apply_github_prefix
from mikazuki.tasks import tm, LANE_MAINTENANCE, TaskStatus
from .diagnose import actions_for_diagnosis, diagnose
from .environment import (
    deps_install_commands,
    install_commands,
    process_env,
    python_install_command,
    venv_install_commands,
)
from .extension_state import fingerprint_facts, write_state
from .manifest import UPSTREAM

VALID_REPAIR_ACTIONS = {
    "refresh_state",
    "repair_source",
    "repair_venv",
    "repair_venv_deps",
    "repair_python_runtime",
    "full_reinstall",
}


def assert_idle(maintenance_only=False):
    if any(
        (not maintenance_only or t.metadata.get("kind") == "diffsynth_install")
        and t.metadata.get("backend") == "diffsynth"
        and t.status in {TaskStatus.CREATED, TaskStatus.QUEUED, TaskStatus.RUNNING}
        for t in tm.tasks.values()
    ):
        raise ValueError("DiffSynth 任务尚未结束，请先停止任务。")


def source_clone_commands(runtime, sources):
    return [
        ["git", "clone", "--no-checkout", apply_github_prefix(UPSTREAM["github"], sources.github_url_prefix), str(runtime.source)],
        ["git", "-C", str(runtime.source), "checkout", "--detach", UPSTREAM["commit"]],
    ]


def installation_plan(runtime, sources):
    return [*source_clone_commands(runtime, sources), *install_commands(runtime, sources)]


def _delete_paths_for_actions(runtime, actions: list[str]) -> list[str]:
    paths: list[Path] = []
    if "full_reinstall" in actions:
        paths = [runtime.source, runtime.root / ".venv", runtime.python_install_dir]
    else:
        if "repair_python_runtime" in actions:
            paths.extend([runtime.python_install_dir, runtime.root / ".venv"])
        elif "repair_venv" in actions:
            paths.append(runtime.root / ".venv")
        # repair_source / repair_venv_deps / refresh_state delete nothing by default
    return [str(path) for path in paths]


def build_repair_plan(runtime, sources, actions: list[str], diagnosis: dict | None = None) -> dict:
    """Describe what a repair will do (for dry_run and the worker)."""
    steps: list[dict] = []
    for action in actions:
        if action == "fresh_install":
            steps.append({"action": action, "commands": installation_plan(runtime, sources)})
        elif action == "full_reinstall":
            steps.append(
                {
                    "action": action,
                    "delete": [str(runtime.source), str(runtime.root / ".venv"), str(runtime.python_install_dir)],
                    "commands": installation_plan(runtime, sources),
                }
            )
        elif action == "repair_source":
            if runtime.source.exists():
                commands = [
                    ["git", "-C", str(runtime.source), "fetch", "origin", UPSTREAM["commit"]],
                    ["git", "-C", str(runtime.source), "checkout", "--detach", UPSTREAM["commit"]],
                ]
            else:
                commands = source_clone_commands(runtime, sources)
            steps.append({"action": action, "commands": commands})
        elif action == "repair_python_runtime":
            steps.append(
                {
                    "action": action,
                    "delete": [str(runtime.python_install_dir), str(runtime.root / ".venv")],
                    "commands": [python_install_command(runtime, sources), *venv_install_commands(runtime, sources)],
                }
            )
        elif action == "repair_venv":
            steps.append(
                {
                    "action": action,
                    "delete": [str(runtime.root / ".venv")],
                    "commands": venv_install_commands(runtime, sources),
                }
            )
        elif action == "repair_venv_deps":
            steps.append({"action": action, "commands": deps_install_commands(runtime, sources)})
        elif action == "refresh_state":
            steps.append({"action": action, "commands": []})
        else:
            raise ValueError(f"未知修复动作: {action}")
    return {
        "actions": actions,
        "steps": steps,
        "delete": _delete_paths_for_actions(runtime, actions),
        "diagnosis": diagnosis,
        "summary": " → ".join(actions),
    }


def _spawn_task(runtime, plan: dict, *, job_label: str) -> dict:
    import sys
    from .resource import request_lock

    with request_lock:
        assert_idle()
        task_id = f"diffsynth-install-{uuid.uuid4()}"
        plan_path = runtime.project_root / "config" / "autosave" / f"{task_id}.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_payload = {**plan, "task_id": task_id}
        plan_path.write_text(json.dumps(plan_payload, ensure_ascii=False), encoding="utf-8")
        command = [
            sys.executable,
            str(Path(__file__).with_name("install_worker.py")),
            str(runtime.project_root),
            str(plan_path),
            task_id,
        ]
        task = tm.create_task(
            command,
            process_env(),
            metadata={"backend": "diffsynth", "kind": "diffsynth_install", "job_label": job_label},
            task_id=task_id,
            lane=LANE_MAINTENANCE,
        )
        write_state(
            runtime,
            "installing",
            {
                "task_id": task_id,
                "repair": {
                    "actions": plan.get("actions") or [],
                    "diagnosis": (plan.get("diagnosis") or {}).get("code"),
                },
            },
        )
        task.execute()
        threading.Thread(target=task.wait, daemon=True).start()
    return {
        "task_id": task_id,
        "log_stream": f"/api/engines/diffsynth/install/log/stream/{task_id}",
        "progress_stream": f"/api/engines/diffsynth/install/progress/stream/{task_id}",
        "plan": {
            "actions": plan.get("actions"),
            "delete": plan.get("delete"),
            "summary": plan.get("summary"),
            "diagnosis": plan.get("diagnosis"),
        },
    }


def start_install(runtime, sources=None, repair=False):
    """Fresh install. ``repair=True`` kept as alias for full_reinstall (legacy)."""
    sources = sources or DownloadSources()
    if repair:
        return start_full_reinstall(runtime, sources)
    plan = {
        "actions": ["fresh_install"],
        "steps": [{"action": "fresh_install", "commands": installation_plan(runtime, sources)}],
        "delete": [],
        "commands": installation_plan(runtime, sources),  # legacy worker field
        "repair": False,
    }
    return _spawn_task(runtime, plan, job_label="安装 DiffSynth")


def start_full_reinstall(runtime, sources=None):
    sources = sources or DownloadSources()
    plan = build_repair_plan(runtime, sources, ["full_reinstall"])
    plan["repair"] = True  # legacy worker wipe flag
    plan["commands"] = installation_plan(runtime, sources)
    return _spawn_task(runtime, plan, job_label="完整重装 DiffSynth")


def refresh_state_sync(runtime) -> dict:
    """Audit once and persist ready/broken without a background task."""
    from .environment import audit_environment

    write_state(runtime, "auditing", {"recovery": "refresh_state"})
    audit = audit_environment(runtime)
    if not audit.get("ok"):
        reason = "; ".join(audit.get("errors") or ["环境审计失败"])
        write_state(runtime, "broken", {"recovery": "refresh_state", "audit": audit}, reason)
        return {"state": "broken", "facts": {"audit": audit}, "reason": reason}
    facts = {
        "recovery": "refresh_state",
        "audit": audit,
        "source_commit": UPSTREAM["commit"],
        **fingerprint_facts(runtime),
    }
    reason = "环境审计通过，状态已刷新"
    write_state(runtime, "ready", facts, reason)
    return {"state": "ready", "facts": facts, "reason": reason}


def start_surgical_repair(runtime, sources=None, *, action: str | None = None, dry_run: bool = False):
    """Diagnose and run the minimal repair chain (#462)."""
    sources = sources or DownloadSources()
    diagnosis = diagnose(runtime)
    actions = actions_for_diagnosis(diagnosis, explicit=action if action in VALID_REPAIR_ACTIONS else None)

    if diagnosis["code"] == "missing_all" or actions == ["fresh_install"]:
        raise ValueError("DiffSynth 尚未安装，请先执行安装，而不是修复。")
    if diagnosis["code"] == "host_no_gpu":
        raise ValueError("未检测到 CUDA GPU。这不是仓库内环境损坏，完整重装也无法解决；请检查驱动与 GPU。")
    if diagnosis["code"] == "healthy" and not action:
        from .extension_state import read_status

        return {"already_ready": True, "status": read_status(runtime), "diagnosis": diagnosis}
    if not actions:
        raise ValueError(f"无法自动修复：{diagnosis.get('summary')}")

    plan = build_repair_plan(runtime, sources, actions, diagnosis)
    if dry_run:
        return {"dry_run": True, "plan": plan, "diagnosis": diagnosis}

    # Sync fast-path: only refresh_state
    if actions == ["refresh_state"]:
        status = refresh_state_sync(runtime)
        from .extension_state import read_status

        return {
            "already_ready": status.get("state") == "ready",
            "status": read_status(runtime),
            "diagnosis": diagnosis,
            "plan": {"actions": actions, "summary": plan["summary"], "delete": []},
        }

    return _spawn_task(runtime, plan, job_label=f"修复 DiffSynth（{plan['summary']}）")


def remove_extension(runtime):
    from .resource import request_lock, environment_lock

    with request_lock:
        assert_idle()
        with environment_lock(runtime.root):
            if runtime.root.exists():
                shutil.rmtree(runtime.root)

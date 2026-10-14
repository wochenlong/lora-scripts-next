"""Task-owned installer / surgical-repair supervisor (#462)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from mikazuki.download_sources import DownloadSources
from mikazuki.engines.diffsynth.environment import audit_environment, install_env, venv_install_commands
from mikazuki.engines.diffsynth.extension_state import fingerprint_facts, write_state
from mikazuki.engines.diffsynth.manifest import UPSTREAM
from mikazuki.engines.diffsynth.resource import environment_lock
from mikazuki.engines.diffsynth.settings import Runtime


def _progress(percent: int, message: str) -> None:
    print(
        "[mikazuki-progress] "
        + json.dumps({"percent": percent, "message": message}, ensure_ascii=False),
        flush=True,
    )


def _run_commands(rt: Runtime, commands: list[list[str]], *, base_percent: int, span: int) -> None:
    total = max(len(commands), 1)
    for index, command in enumerate(commands):
        percent = base_percent + int(index * span / total)
        _progress(percent, " ".join(command))
        print("[install] " + " ".join(command), flush=True)
        subprocess.run(command, env=install_env(rt), check=True)


def _delete(paths: list[str]) -> None:
    for raw in paths:
        path = Path(raw)
        if path.exists():
            print(f"[repair] remove {path}", flush=True)
            shutil.rmtree(path)


def _refresh_state(rt: Runtime, facts: dict) -> None:
    write_state(rt, "auditing", facts)
    _progress(92, "环境审计")
    audit = audit_environment(rt)
    print(json.dumps(audit, ensure_ascii=False), flush=True)
    if not audit.get("ok"):
        raise RuntimeError("; ".join(audit.get("errors") or ["环境审计失败"]))
    write_state(
        rt,
        "ready",
        {**facts, "audit": audit, "source_commit": UPSTREAM["commit"], **fingerprint_facts(rt)},
    )
    _progress(100, "环境检查完成")


def _adapt_source_commands(rt: Runtime, commands: list[list[str]]) -> list[list[str]]:
    """If source already exists, replace git clone with fetch + keep checkout/deps."""
    if (
        rt.source.exists()
        and commands
        and len(commands[0]) >= 2
        and commands[0][0] == "git"
        and commands[0][1] == "clone"
    ):
        return [
            ["git", "-C", str(rt.source), "fetch", "origin", UPSTREAM["commit"]],
            *commands[1:],
        ]
    return commands


def _run_step(rt: Runtime, step: dict, *, base_percent: int, span: int) -> None:
    _delete(step.get("delete") or [])
    commands = _adapt_source_commands(rt, list(step.get("commands") or []))
    _run_commands(rt, commands, base_percent=base_percent, span=span)


def _execute_steps(rt: Runtime, plan: dict, facts: dict) -> None:
    steps = list(plan.get("steps") or [])
    if not steps:
        if plan.get("repair"):
            _delete([str(rt.source), str(rt.root / ".venv"), str(rt.python_install_dir)])
        commands = _adapt_source_commands(rt, list(plan.get("commands") or []))
        _run_commands(rt, commands, base_percent=0, span=90)
        _refresh_state(rt, facts)
        return

    skipped_venv = False
    total = max(len(steps), 1)
    for index, step in enumerate(steps):
        action = step.get("action")
        if action == "repair_venv" and skipped_venv:
            continue
        facts = {**facts, "repair_step": action}
        write_state(rt, "installing", facts)
        base = int(index * 80 / total)
        span = max(10, 80 // total)

        if action == "refresh_state":
            _refresh_state(rt, facts)
            return

        try:
            _run_step(rt, step, base_percent=base, span=span)
        except Exception:
            if action != "repair_venv_deps":
                raise
            print("[repair] repair_venv_deps failed; escalating to repair_venv", flush=True)
            escalated = next((s for s in steps[index + 1 :] if s.get("action") == "repair_venv"), None)
            if escalated is None:
                escalated = {
                    "action": "repair_venv",
                    "delete": [str(rt.root / ".venv")],
                    "commands": venv_install_commands(rt, DownloadSources()),
                }
            else:
                skipped_venv = True
            _run_step(rt, escalated, base_percent=min(base + 10, 80), span=20)

    _refresh_state(rt, facts)


def main():
    rt = Runtime(Path(sys.argv[1]))
    plan = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    facts = {
        "task_id": sys.argv[3],
        "repair": {
            "actions": plan.get("actions") or [],
            "diagnosis": (plan.get("diagnosis") or {}).get("code"),
        },
    }
    with environment_lock(rt.root):
        try:
            _execute_steps(rt, plan, facts)
        except Exception as exc:
            write_state(rt, "broken", facts, str(exc))
            raise


if __name__ == "__main__":
    main()

"""Cancellable task supervisor; all subprocess execution is injectable in tests."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mikazuki.download_sources import DownloadSources
from mikazuki.engines.moss.environment import audit_environment, install_env
from mikazuki.engines.moss.extension_state import fingerprint_facts, write_state
from mikazuki.engines.moss.manifest import UPSTREAM
from mikazuki.engines.moss.resource import environment_lock
from mikazuki.engines.moss.settings import Runtime


def _progress(percent, message):
    print("[mikazuki-progress] " + json.dumps({"percent": percent, "message": message}, ensure_ascii=False), flush=True)


def execute_plan(runtime, plan, task_id, *, runner=None, audit_fn=None):
    """Run planned commands, recording failures so a later install can retry.

    Repair recreates only this engine's managed source/.venv/.python. Model,
    dataset, output and cache directories outside these three are preserved.
    """
    run = runner or subprocess.run
    audit = audit_fn or audit_environment
    facts = {"task_id": task_id, "repair": bool(plan.get("repair")), "source_commit": UPSTREAM["commit"]}
    try:
        with environment_lock(runtime.root):
            write_state(runtime, "installing", facts)
            if plan.get("repair"):
                for path in (runtime.source, runtime.root / ".venv", runtime.python_install_dir):
                    if path.is_symlink():
                        path.unlink()
                    elif path.exists():
                        shutil.rmtree(path)
            commands = [list(command) for command in plan["commands"]]
            if runtime.source.exists() and commands and commands[0][:2] == ["git", "clone"]:
                if (runtime.source / ".git").is_dir():
                    commands[0] = ["git", "-C", str(runtime.source), "fetch", "origin", UPSTREAM["commit"]]
                else:
                    # A failed clone can leave an incomplete destination.
                    shutil.rmtree(runtime.source)
            sources = DownloadSources(**(plan.get("download_sources") or {}))
            for index, command in enumerate(commands):
                facts["phase"] = "commands"
                facts["command_index"] = index
                write_state(runtime, "installing", facts)
                _progress(int(index * 88 / max(len(commands), 1)), " ".join(command))
                run(command, cwd=runtime.project_root, env=install_env(runtime, sources), check=True)
            facts["phase"] = "audit"
            write_state(runtime, "auditing", facts)
            _progress(92, "审计 MOSS 请求解析器、训练/缓存入口和 CUDA 环境")
            result = audit(runtime)
            facts["audit"] = result
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if not result.get("ok"):
                raise RuntimeError("; ".join(result.get("errors") or ["MOSS 环境审计失败。"]))
            facts.update(fingerprint_facts(runtime))
            facts["phase"] = "ready"
            write_state(runtime, "ready", facts)
            _progress(100, "MOSS 环境检查完成")
            return result
    except Exception as exc:
        # Do not overwrite another process's install state if its lock is held.
        if not isinstance(exc, ValueError) or "正在使用中" not in str(exc):
            write_state(runtime, "broken", facts, str(exc))
        raise


def main():
    runtime = Runtime(Path(sys.argv[1]).resolve())
    plan = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    execute_plan(runtime, plan, sys.argv[3])


if __name__ == "__main__":
    main()

"""Cancellable installer worker for the isolated runtime."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mikazuki.download_sources import DownloadSources
from mikazuki.engines.kohaku_moss.environment import audit_environment, install_env
from mikazuki.engines.kohaku_moss.extension_state import write_state
from mikazuki.engines.kohaku_moss.manifest import UPSTREAM
from mikazuki.engines.kohaku_moss.resource import environment_lock
from mikazuki.engines.kohaku_moss.settings import INSTALL_REVISION, Runtime
from mikazuki.networking import redact


def progress(percent, message):
    print("[mikazuki-progress] " + json.dumps({"percent": percent, "message": message}, ensure_ascii=False), flush=True)


def execute_plan(runtime, plan, task_id):
    facts = {"task_id": task_id, "source_commit": UPSTREAM["commit"], "install_revision": INSTALL_REVISION}
    with environment_lock(runtime.root):
        try:
            if plan.get("repair"):
                for path in (runtime.source, runtime.root / ".venv", runtime.python_install_dir):
                    if path.exists():
                        shutil.rmtree(path)
            commands = [list(command) for command in plan["commands"]]
            if runtime.source.exists() and commands and commands[0][:2] == ["git", "clone"]:
                if (runtime.source / ".git").is_dir():
                    commands[0] = ["git", "-C", str(runtime.source), "fetch", "origin", UPSTREAM["commit"]]
                else:
                    # A failed clone may leave an incomplete managed source directory.
                    shutil.rmtree(runtime.source)
            sources = DownloadSources(**(plan.get("download_sources") or {}))
            for index, command in enumerate(commands):
                progress(int(index * 88 / max(len(commands), 1)), redact(" ".join(command)))
                subprocess.run(command, cwd=runtime.project_root, env=install_env(runtime, sources), check=True)
            write_state(runtime, "auditing", facts)
            progress(92, "审计 KohakuMossTrainer、LyCORIS 与 CUDA")
            audit = audit_environment(runtime)
            facts["audit"] = audit
            if not audit["ok"]:
                raise RuntimeError("; ".join(audit["errors"]))
            write_state(runtime, "ready", facts)
            progress(100, "KohakuMossTrainer 环境检查完成")
        except Exception as exc:
            write_state(runtime, "broken", facts, str(exc))
            raise


def main():
    runtime = Runtime(Path(sys.argv[1]).resolve())
    plan = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    execute_plan(runtime, plan, sys.argv[3])


if __name__ == "__main__":
    main()

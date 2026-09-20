"""SDK downloads run in an isolated process with one immutable network env."""
import json
import os
from pathlib import Path
import subprocess
import sys

from .policy import resolve_policy, redact, config_path


def download_models(train_type, items, source, project_root: Path, log):
    policy = resolve_policy()
    log(f"[network] {policy.diagnostic()}")
    env = policy.process_env()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["NEXT_TRAINER_NETWORK_CONFIG"] = str(config_path().resolve())
    # Explicit source root also works with portable Python's isolated _pth.
    script = Path(__file__).resolve().with_name("model_worker.py")
    process = subprocess.Popen([sys.executable, str(script)], cwd=str(project_root), env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace")
    try:
        process.stdin.write(json.dumps({"train_type": train_type, "items": items, "source": source,
                                       "project_root": str(project_root)}))
        process.stdin.close()
        for line in process.stdout:
            log(redact(line.rstrip()))
        code = process.wait()
        if code:
            raise RuntimeError(f"模型下载失败（退出码 {code}），请查看上方下载日志。")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()

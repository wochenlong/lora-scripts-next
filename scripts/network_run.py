"""Portable/CLI bridge to the same Python network policy (stdlib only)."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    from mikazuki.networking.policy import resolve_policy, original_proxy_env, ORIGINAL_PROXY_ENV
    os.environ.setdefault("NEXT_TRAINER_NETWORK_CONFIG", str(ROOT / "config" / "network.local.json"))
    policy = resolve_policy()
    env = policy.process_env()
    env[ORIGINAL_PROXY_ENV] = json.dumps(original_proxy_env(dict(os.environ)))
    if sys.argv[1:] == ["--env-json"]:
        print(json.dumps({key: env.get(key, "") for key in
                          ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", ORIGINAL_PROXY_ENV)}))
        return 0
    command = sys.argv[1:]
    batch = command[:1] == ["--batch"]
    if batch:
        command = command[1:]
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        print(json.dumps(policy.diagnostic(), ensure_ascii=False))
        return 0
    env["NEXT_TRAINER_NETWORK_READY"] = "1"
    print("[network] " + json.dumps(policy.diagnostic(), ensure_ascii=False), flush=True)
    if batch:
        # Pass one cmd command string, not list2cmdline's backslash-escaped
        # embedded quotes (cmd.exe does not use the C argv quoting rules).
        if any('"' in arg or '\n' in arg or '\r' in arg for arg in command):
            raise ValueError("Batch arguments may not contain quotes or newlines")
        quoted = " ".join('"' + arg + '"' for arg in command)
        cmd = '"' + os.environ.get("COMSPEC", "cmd.exe") + '" /d /s /c "' + quoted + '"'
        return subprocess.call(cmd, env=env)
    return subprocess.call(command, env=env)

if __name__ == "__main__":
    sys.exit(main())

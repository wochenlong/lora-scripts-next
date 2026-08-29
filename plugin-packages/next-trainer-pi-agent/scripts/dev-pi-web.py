# /// script
# requires-python = ">=3.11"
# ///
"""Fast dev loop for next-trainer-pi-web — no packaging, no host reinstall.

Run from project/ with the venv python (same as the other scripts):

  .venv-dev\\Scripts\\python.exe plugin-packages\\next-trainer-pi-agent\\scripts\\dev-pi-web.py

Modes (pick one):
  (default / --dev)     Next.js HMR dev server straight from the working tree
                        (pi-web/). Edits hot-reload in the browser. This is the
                        everyday loop: edit -> save -> refresh.
  --built               Serve the PACKAGED build (pi-web/.next + bin/pi-web.js)
                        from the working tree with the embedded Node version.
                        Catches build-only regressions without zipping. Stop
                        the HMR dev server first (never run `next build` / the
                        HMR server concurrently — pi-web AGENTS.md).
  --launcher            Full launcher contract preview from the working tree
                        (recompile bin EXE via bun, then run the real contract:
                        ephemeral port, READY line, Bearer /health, uiUrl).
                        Ctrl+C exits; the launcher's parent-death monitor then
                        tears down the pi-web tree and we verify 0 leftovers.

Options:
  --port N              dev/built port (defaults: dev 30141, built 30142)
  --agent-dir PATH      PI_CODING_AGENT_DIR. Default: the installed plugin
                        instance's agent dir (same sessions as the host
                        floating dialog) when it exists, else an isolated
                        .runtime/dev/agent scratch dir.

Environment isolation (all modes): HOME/USERPROFILE/APPDATA/TMP are pinned
under .runtime/dev/ so dev never touches your real profile; only the pi agent
dir is shared by default (pass --agent-dir for a fully isolated run).

Do NOT run this next to `build-all-platforms.py` (both write pi-web/.next).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PKG_ROOT = SCRIPT_DIR.parent
PIWEB = PKG_ROOT / "pi-web"
PROJECT_ROOT = PKG_ROOT.parents[1]

def _node_runtime() -> Path:
    """Node directory (node.exe + node_modules/npm/bin/npm-cli.js layout).
    Set PI_WEB_NODE_RUNTIME, or keep Node >= 22 on PATH."""
    import shutil
    raw = os.environ.get("PI_WEB_NODE_RUNTIME", "").strip()
    if raw:
        return Path(raw)
    found = shutil.which("node")
    return Path(found).resolve().parent if found else Path(".")

NODE_RUNTIME = _node_runtime()
NPM_CLI = NODE_RUNTIME / "node_modules" / "npm" / "bin" / "npm-cli.js"
BUN_VERSION = "1.4.0"

DEV_ROOT = PKG_ROOT / ".runtime" / "dev"
BUNDLED_NODE = PKG_ROOT / "runtime" / "node" / ("node.exe" if os.name == "nt" else "node")
INSTALLED_AGENT_DIR = (
    PROJECT_ROOT / ".runtime" / "plugin-marketplace" / "data" / "next-trainer-pi-agent" / "pi-agent"
)


class DevError(RuntimeError):
    pass


def banner(title: str, lines: list[str]) -> None:
    print(f"\n=== {title} ===")
    for line in lines:
        print(f"  {line}")
    print(flush=True)


def require_node() -> Path:
    node = NODE_RUNTIME / ("node.exe" if os.name == "nt" else "node")
    if not node.is_file():
        raise DevError(f"missing dev Node runtime: {NODE_RUNTIME} (run build-pi-web-package.py once to provision)")
    return node


def require_node_modules() -> None:
    if (PIWEB / "node_modules" / "next" / "package.json").is_file():
        return
    print("[dev] pi-web/node_modules missing — running npm ci (2-4 min, once) ...", flush=True)
    node = require_node()
    result = subprocess.run([str(node), str(NPM_CLI), "ci", "--no-audit", "--no-fund"], cwd=str(PIWEB))
    if result.returncode != 0:
        raise DevError("npm ci failed in the pi-web working tree")


def isolated_env(agent_dir: Path) -> dict[str, str]:
    """Containment env matching the launcher's child env (launcher/src/main.ts)."""
    home = DEV_ROOT / "home"
    tmp = DEV_ROOT / "tmp"
    home.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    agent_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "PI_CODING_AGENT_DIR": str(agent_dir),
            "PI_WEB_NO_OPEN": "1",
            # Next Trainer pi package (extensions + skills) + knowledge/template
            # data root, so the dev server loads the same assets the packaged
            # plugin would (pi-web bootstrap registers the package on first
            # session; the knowledge tool reads the data root on every call).
            "NEXT_TRAINER_PI_PACKAGE_ROOT": str(PKG_ROOT / "pi-package"),
            "NEXT_TRAINER_PLUGIN_DATA_ROOT": str(DEV_ROOT / "data-root"),
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(home / "AppData" / "Roaming"),
            "LOCALAPPDATA": str(home / "AppData" / "Local"),
            "TMP": str(tmp),
            "TEMP": str(tmp),
        }
    )
    return env


def pick_agent_dir(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser().resolve()
    if (INSTALLED_AGENT_DIR / "sessions").is_dir():
        return INSTALLED_AGENT_DIR
    return DEV_ROOT / "agent"


def kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            import signal
            import os as _os
            _os.killpg(pid, signal.SIGKILL)
        except OSError:
            try:
                _os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def wait_http(url: str, timeout: float = 120.0) -> int:
    deadline = time.time() + timeout
    last = "no response"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status
        except Exception as exc:  # noqa: BLE001 — retry until deadline
            last = str(exc)
        time.sleep(1)
    raise DevError(f"{url} did not answer within {timeout:.0f}s ({last})")


# ---------------------------------------------------------------------------
# --dev / --built
# ---------------------------------------------------------------------------

def seed_dev_data_root() -> None:
    """Idempotently copy the package's knowledge/template seeds into the dev
    data root. Never overwrites or deletes user files (same rule as the
    launcher), so the user can add their own md/toml under .runtime/dev/data-root.
    """
    seeds = PKG_ROOT / "seeds"
    data_root = DEV_ROOT / "data-root"
    if not seeds.is_dir():
        return
    for sub in ("knowledge", "templates"):
        src = seeds / sub
        if not src.is_dir():
            continue
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            target = data_root / sub / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(path, target)


def register_pi_package(agent_dir: Path) -> None:
    """Register the Next Trainer pi package into the dev agent dir's pi settings
    so the Plugins/Skills UI shows it immediately — before the first chat session
    would trigger the in-process bootstrap. Best-effort: any failure is logged and
    never blocks dev startup (the in-process bootstrap still runs on first session).
    """
    script = PKG_ROOT / "scripts" / "register-dev-pi-package.mjs"
    if not script.is_file():
        return
    try:
        subprocess.run(
            [str(require_node()), str(script), "--agent-dir", str(agent_dir)],
            cwd=str(PIWEB),
            timeout=90,
        )
    except Exception as exc:  # noqa: BLE001 - dev convenience must never break boot
        print(f"[dev] pi package registration skipped: {exc}", flush=True)


def run_server(mode: str, port: int, agent_dir: Path) -> int:
    node = require_node()
    require_node_modules()
    seed_dev_data_root()
    register_pi_package(agent_dir)
    env = isolated_env(agent_dir)

    if mode == "dev":
        cmd = [str(node), str(PIWEB / "node_modules" / "next" / "dist" / "bin" / "next"),
               "dev", "-H", "127.0.0.1", "-p", str(port)]
        title = "pi-web HMR dev server (working tree)"
        note = "edits hot-reload; do NOT run `next build` or build-all-platforms.py concurrently"
    else:
        if not (PIWEB / ".next" / "BUILD_ID").is_file():
            raise DevError("no packaged .next in the working tree — run build-all-platforms.py (or npm run build) first")
        cmd = [str(node), str(PIWEB / "bin" / "pi-web.js"), "-H", "127.0.0.1", "-p", str(port), "--no-open"]
        title = "pi-web packaged build preview (working tree .next)"
        note = "this serves the same .next the win zip would ship (stop the HMR server first)"

    banner(
        title,
        [
            f"URL        http://127.0.0.1:{port}/",
            f"agent dir  {agent_dir}",
            f"isolated   HOME/APPDATA/TMP under {DEV_ROOT}",
            note,
            "Ctrl+C to stop",
        ],
    )
    child = subprocess.Popen(cmd, cwd=str(PIWEB), env=env)
    try:
        status = wait_http(f"http://127.0.0.1:{port}/", timeout=240)
        print(f"\n[serving] http 200 check: {status} — open http://127.0.0.1:{port}/ \n", flush=True)
        child.wait()
        return 0
    except KeyboardInterrupt:
        print("\n[dev] stopping ...", flush=True)
        kill_tree(child.pid)
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        return 0


# ---------------------------------------------------------------------------
# --launcher
# ---------------------------------------------------------------------------

def find_bun() -> Path:
    pattern = os.path.join(os.environ.get("LOCALAPPDATA", ""), "npm-cache", "_npx", "*", "node_modules", "bun", "bin", "bun.exe")
    candidates = sorted((Path(p) for p in glob.glob(pattern)), key=lambda p: p.stat().st_mtime, reverse=True)
    for candidate in candidates:
        try:
            out = subprocess.run([str(candidate), "--version"], capture_output=True, text=True, timeout=30)
            if out.returncode == 0 and out.stdout.strip() == BUN_VERSION:
                return candidate
        except (OSError, subprocess.SubprocessError):
            continue
    raise DevError(f"could not locate bun {BUN_VERSION} (expected under %LOCALAPPDATA%\\npm-cache\\_npx)")


def run_launcher(agent_dir: Path) -> int:
    # 1) bundled node for the working tree (one-time copy, gitignored).
    if not BUNDLED_NODE.is_file():
        source = NODE_RUNTIME / ("node.exe" if os.name == "nt" else "node")
        if not source.is_file():
            raise DevError(f"missing dev Node runtime: {NODE_RUNTIME}")
        BUNDLED_NODE.parent.mkdir(parents=True, exist_ok=True)
        print(f"[launcher] provisioning {BUNDLED_NODE.name} from {source} ...", flush=True)
        shutil.copy2(source, BUNDLED_NODE)

    # 2) recompile the win EXE so the preview always matches main.ts.
    bun = find_bun()
    print(f"[launcher] compiling {bun.name} -> bin/next-trainer-pi-agent.exe ...", flush=True)
    result = subprocess.run(
        [str(bun), "build", str(PKG_ROOT / "launcher" / "src" / "main.ts"), "--compile",
         "--target=bun-windows-x64", "--outfile", str(PKG_ROOT / "bin" / "next-trainer-pi-agent.exe")],
        timeout=600,
    )
    if result.returncode != 0:
        raise DevError("bun compile failed")

    # 3) run the real contract against the working tree.
    data_root = DEV_ROOT / "launcher-data"
    token = secrets.token_hex(24)
    env = os.environ.copy()
    env.update(
        {
            "NEXT_TRAINER_PLUGIN_DATA_ROOT": str(data_root),
            "NEXT_TRAINER_SIDECAR_TOKEN": token,
            "NEXT_TRAINER_PARENT_PID": str(os.getpid()),
            "NEXT_TRAINER_SIDECAR_PORT": "0",
        }
    )
    child = subprocess.Popen(
        [str(PKG_ROOT / "bin" / "next-trainer-pi-agent.exe")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(PKG_ROOT),
    )
    ready: dict | None = None
    deadline = time.time() + 180
    assert child.stdout is not None
    while time.time() < deadline:
        line = child.stdout.readline()
        if not line:
            if child.poll() is not None:
                raise DevError("launcher exited before READY")
            continue
        stripped = line.strip()
        if stripped:
            print(f"  {stripped[:200]}", flush=True)
        if stripped.startswith("{") and '"READY"' in stripped:
            ready = json.loads(stripped)
            break
    if ready is None:
        kill_tree(child.pid)
        raise DevError("no READY line within 180s")

    health_url = f"http://127.0.0.1:{ready['port']}/health"
    request = urllib.request.Request(health_url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=10) as response:
        health = json.loads(response.read().decode())
    ui_code = wait_http(ready["uiUrl"] + "/", timeout=240)

    banner(
        "launcher contract preview (working tree, ephemeral ports)",
        [
            f"READY      port={ready['port']} uiUrl={ready['uiUrl']} childPid={ready.get('childPid')}",
            f"health     {health.get('ok')} status={health.get('data', {}).get('status')} version={health.get('data', {}).get('version')}",
            f"uiUrl      http {ui_code}",
            f"data root  {data_root}",
            "Ctrl+C to stop (the launcher's parent-death monitor tears the tree down)",
        ],
    )
    try:
        child.wait()
    except KeyboardInterrupt:
        print("\n[launcher] parent (this process) exiting — launcher should self-terminate ...", flush=True)
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            kill_tree(child.pid)
            child.wait(timeout=15)
        time.sleep(2)
        # 0-leftover check scoped to this preview's data root (global counts
        # would include concurrently running host instances).
        try:
            wmi = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process -Filter \"Name like 'node%'\" | "
                 f"Where-Object {{ $_.CommandLine -like '*{data_root}*pi-web.js*' }} | Measure-Object | Select-Object -ExpandProperty Count"],
                capture_output=True, text=True, timeout=60,
            )
            leftovers = (wmi.stdout or "1").strip()
        except Exception:  # noqa: BLE001
            leftovers = "?"
        print(f"\n[launcher] shutdown complete, leftover pi-web (scoped): {leftovers}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dev", action="store_true", help="HMR dev server (default)")
    parser.add_argument("--built", action="store_true", help="serve the packaged .next build")
    parser.add_argument("--launcher", action="store_true", help="full launcher contract preview")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--agent-dir", default=None, help="PI_CODING_AGENT_DIR (default: installed instance dir when present)")
    args = parser.parse_args()

    if args.launcher:
        mode = "launcher"
    elif args.built:
        mode = "built"
    else:
        mode = "dev"

    try:
        if mode == "launcher":
            return run_launcher(pick_agent_dir(args.agent_dir))
        port = args.port or (30141 if mode == "dev" else 30142)
        return run_server(mode, port, pick_agent_dir(args.agent_dir))
    except DevError as exc:
        print(f"\nDEV RUN FAILED: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

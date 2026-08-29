# /// script
# requires-python = ">=3.11"
# ///
"""Dual-platform package pipeline (CR-012) — one command, stable re-runs.

After editing the plugin, run this to rebuild BOTH platform packages and the
dual-platform dev catalog:

  .venv-dev\\Scripts\\python.exe plugin-packages\\next-trainer-pi-agent\\scripts\\build-all-platforms.py

Modes:
  (default)          full: launchers + pi-web (win + linux) + both zips + catalog
  --launcher-only    rebuild launchers only, then re-zip both packages + catalog
                     (fast path for launcher/src/main.ts edits; reuses the WSL
                     build tree when present, otherwise falls back to a full
                     linux build)
  --piweb-only       rebuild pi-web on both platforms, then re-zip + catalog
                     (uses the existing launcher binaries in bin/)

What each mode does (details in scripts/PIPELINE.md):
  1. locate bun 1.4.0 (npx cache, version-verified; fetches on miss)
  2. build launcher: bin/next-trainer-pi-agent.exe (win32) +
     bin/next-trainer-pi-agent (linux-x64 ELF)
  3. win:  `npm run build` in pi-web/ (fresh .next from the working tree)
  4. win:  build-pi-web-package.py --zip-only (stage + prune + zip)
  5. linux: source tar -> WSL (npm ci + next build + prune + strip + smoke)
            -> stage + zip inside WSL (only the zip crosses the 9p bridge)
  6. build-marketplace-catalog.py (dual catalog + per-platform self-check)
  7. drop the stale dev catalog cache so a running dev backend serves the
     new catalog on its next refresh

Expected duration: full ~20-25 min, launcher-only ~10 min (fast when the WSL
tree is warm), piweb-only ~15 min.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PKG_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = PKG_ROOT.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

VERSION = "0.3.2"
PLUGIN_ID = "next-trainer-pi-agent"
BUN_VERSION = "1.4.0"
WSL_DISTRO = "kali-linux"

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

WSL_BUILD_SH = SCRIPT_DIR / "wsl" / "wsl-build-pi-web.sh"
WSL_STAGE_SH = SCRIPT_DIR / "wsl" / "wsl-stage-linux-package.sh"

SRC_TAR = PKG_ROOT / ".runtime" / "linux-src.tar.gz"
WIN_ZIP = PKG_ROOT / "dist-marketplace" / "packages" / f"{PLUGIN_ID}-{VERSION}-win32-x64.zip"
LINUX_ZIP = PKG_ROOT / "dist-marketplace" / "packages" / f"{PLUGIN_ID}-{VERSION}-linux-x64.zip"
CATALOG_BUILDER = SCRIPT_DIR / "build-marketplace-catalog.py"
WIN_PACKAGER = SCRIPT_DIR / "build-pi-web-package.py"


class PipelineError(RuntimeError):
    pass


def step(n: int, total: int, message: str) -> None:
    print(f"\n[step {n}/{total}] {message}", flush=True)


def run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None, timeout: float | None = None) -> None:
    print(f"$ {' '.join(str(c) for c in cmd)}", flush=True)
    result = subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None, env=env, timeout=timeout)
    if result.returncode != 0:
        raise PipelineError(f"command failed ({result.returncode}): {cmd[0]} ...")


def windows_env() -> dict:
    return {"SystemRoot": r"C:\Windows", "WINDIR": r"C:\Windows", "PATH": r"C:\Windows\System32;C:\Windows"}


def to_wsl_path(path: Path) -> str:
    s = str(path.resolve())
    match = re.match(r"^([A-Za-z]):([\\/].*)?$", s)
    if match:
        return "/mnt/" + match.group(1).lower() + (match.group(2) or "").replace("\\", "/")
    return s


# ---------------------------------------------------------------------------
# 1. bun
# ---------------------------------------------------------------------------

def find_bun() -> Path:
    candidates: list[Path] = []
    pattern = os.path.join(os.environ.get("LOCALAPPDATA", ""), "npm-cache", "_npx", "*", "node_modules", "bun", "bin", "bun.exe")
    candidates = [Path(p) for p in glob.glob(pattern)]

    def verify() -> Path | None:
        for candidate in sorted(candidates, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
            try:
                out = subprocess.run([str(candidate), "--version"], capture_output=True, text=True, timeout=30)
                if out.returncode == 0 and out.stdout.strip() == BUN_VERSION:
                    return candidate
            except (OSError, subprocess.SubprocessError):
                continue
        return None

    found = verify()
    if found:
        return found
    # Fetch the pinned version into the npx cache (cwd without a local
    # node_modules/bun, so npm cannot resolve a shadowing local copy).
    print(f"[bun] no local bun {BUN_VERSION}; fetching via npm exec ...", flush=True)
    subprocess.run(["npm", "exec", "-y", f"bun@{BUN_VERSION}", "--", "--version"], cwd=str(PROJECT_ROOT), check=False)
    candidates = [Path(p) for p in glob.glob(pattern)]
    found = verify()
    if not found:
        raise PipelineError(f"could not locate bun {BUN_VERSION} (npm cache: {pattern})")
    return found


def build_launchers(bun: Path, args: argparse.Namespace) -> None:
    src = PKG_ROOT / "launcher" / "src" / "main.ts"
    if not src.is_file():
        raise PipelineError(f"missing launcher source: {src}")
    targets = [
        ("bun-windows-x64", PKG_ROOT / "bin" / "next-trainer-pi-agent.exe"),
        ("bun-linux-x64", PKG_ROOT / "bin" / "next-trainer-pi-agent"),
    ]
    for target, outfile in targets:
        outfile.parent.mkdir(parents=True, exist_ok=True)
        if args.piweb_only:
            if not outfile.is_file():
                raise PipelineError(f"--piweb-only requires the existing launcher binary {outfile}")
            print(f"[launcher] reusing {outfile.name} (piweb-only mode)", flush=True)
            continue
        run([bun, "build", str(src), "--compile", f"--target={target}", "--outfile", str(outfile)], timeout=600)
        print(f"[launcher] built {outfile.name}", flush=True)


# ---------------------------------------------------------------------------
# 2/3. pi-web
# ---------------------------------------------------------------------------

def build_win_piweb() -> None:
    piweb = PKG_ROOT / "pi-web"
    if not (piweb / "package.json").is_file():
        raise PipelineError(f"missing pi-web working tree: {piweb}")
    if not (NODE_RUNTIME / "node.exe").is_file():
        raise PipelineError(f"missing dev Node runtime: {NODE_RUNTIME} (provisioned by build-pi-web-package.py)")
    env = windows_env()
    # npm-run scripts resolve `node`/`next` through PATH (node_modules/.bin
    # shims invoke plain `node`); put the dev runtime on PATH explicitly so
    # the build never depends on the user's system Node.
    env["PATH"] = r"C:\Windows\System32;C:\Windows;" + str(NODE_RUNTIME)
    # Contained home so Next/npm build side effects stay inside the package
    # scratch dir (same isolation as the original S2 build).
    home = PKG_ROOT / ".runtime" / "win-build-home"
    home.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    run(
        [NODE_RUNTIME / "node.exe", NPM_CLI, "run", "build"],
        cwd=piweb,
        env=env,
        timeout=1800,
    )
    if not (piweb / ".next" / "BUILD_ID").is_file():
        raise PipelineError("pi-web build did not produce .next/BUILD_ID")
    print(f"[win] .next BUILD_ID: {(piweb / '.next' / 'BUILD_ID').read_text(encoding='utf-8').strip()}", flush=True)


def make_source_tar() -> None:
    SRC_TAR.parent.mkdir(parents=True, exist_ok=True)
    if SRC_TAR.exists():
        SRC_TAR.unlink()
    run(
        ["tar", "-a", "-cf", str(SRC_TAR), "-C", str(PKG_ROOT),
         "--exclude=pi-web/node_modules", "--exclude=pi-web/.next", "pi-web"],
        timeout=600,
    )
    listing = subprocess.run(["tar", "-tf", str(SRC_TAR)], capture_output=True, text=True, check=True).stdout
    leaks = [line for line in listing.splitlines() if "node_modules" in line or "/.next/" in line]
    if leaks:
        raise PipelineError(f"source tar leaks {len(leaks)} node_modules/.next entries, e.g. {leaks[:3]}")
    print(f"[linux] source tar: {SRC_TAR.stat().st_size} bytes, 0 excluded-path leaks", flush=True)


def wsl(distro: str, *cmd: str, timeout: float) -> None:
    run(["wsl", "-d", distro, *cmd], timeout=timeout)


def build_linux_piweb(distro: str) -> None:
    # The WSL build is the long pole (~8-12 min cold). Stream output live.
    wsl(distro, "bash", to_wsl_path(WSL_BUILD_SH), to_wsl_path(SRC_TAR), timeout=2400)
    print("[linux] WSL pi-web build complete (smoke included)", flush=True)


def wsl_tree_is_warm(distro: str) -> bool:
    result = subprocess.run(
        ["wsl", "-d", distro, "bash", "-c", "test -d /tmp/nt-pi-linux/src/pi-web/.next && test -x /tmp/nt-pi-linux/node-v22.19.0-linux-x64/bin/node"],
        capture_output=True,
        timeout=120,
    )
    return result.returncode == 0


def stage_linux_zip(distro: str) -> None:
    wsl(distro, "bash", to_wsl_path(WSL_STAGE_SH), timeout=1800)
    if not LINUX_ZIP.is_file():
        raise PipelineError("WSL staging did not produce the linux zip")
    print(f"[linux] zip: {LINUX_ZIP.stat().st_size} bytes", flush=True)


def build_win_zip() -> None:
    run([sys.executable, str(WIN_PACKAGER), "--zip-only"], cwd=PROJECT_ROOT, timeout=2400)
    if not WIN_ZIP.is_file():
        raise PipelineError("win packager did not produce the win zip")
    print(f"[win] zip: {WIN_ZIP.stat().st_size} bytes", flush=True)


# ---------------------------------------------------------------------------
# 6/7. catalog + hygiene
# ---------------------------------------------------------------------------

def build_catalog() -> None:
    run([sys.executable, str(CATALOG_BUILDER)], cwd=PROJECT_ROOT, timeout=900)


def drop_stale_catalog_cache() -> None:
    # The dev backend caches the catalog under .runtime/plugin-marketplace;
    # catalogs signed before a rebuild (or under the pre-CR-012 schema) verify
    # as untrusted there. The cache is disposable: the next refresh repopulates.
    cache = PROJECT_ROOT / ".runtime" / "plugin-marketplace" / "catalog.json"
    if cache.is_file():
        cache.unlink()
        print(f"[hygiene] dropped stale catalog cache: {cache}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--launcher-only", action="store_true", help="rebuild launchers, re-zip both, catalog")
    mode.add_argument("--piweb-only", action="store_true", help="rebuild pi-web (win+linux), re-zip both, catalog")
    parser.add_argument("--distro", default=WSL_DISTRO, help=f"WSL distro name (default: {WSL_DISTRO})")
    args = parser.parse_args()

    total = 7
    started = time.time()

    bun = None
    try:
        if not args.piweb_only:
            step(1, total, f"locate bun {BUN_VERSION} and build both launchers")
            bun = find_bun()
            print(f"[bun] {bun}", flush=True)
            build_launchers(bun, args)
        else:
            step(1, total, "skip launcher rebuild (--piweb-only)")

        if args.launcher_only:
            step(2, total, "skip win pi-web build (--launcher-only)")
            step(3, total, "re-zip win package (launcher-only)")
            build_win_zip()
            step(4, total, "linux: reuse warm WSL tree when present, else full build")
            if not wsl_tree_is_warm(args.distro):
                make_source_tar()
                build_linux_piweb(args.distro)
            stage_linux_zip(args.distro)
            step(5, total, "dual-platform catalog + self-check")
            build_catalog()
            step(6, total, "drop stale dev catalog cache")
            drop_stale_catalog_cache()
            step(7, total, "done")
        else:
            step(2, total, "win: rebuild pi-web .next from the working tree")
            build_win_piweb()

            step(3, total, "win: stage + prune + zip (build-pi-web-package.py --zip-only)")
            build_win_zip()

            step(4, total, "linux: source tar -> WSL build -> stage + zip")
            make_source_tar()
            build_linux_piweb(args.distro)
            stage_linux_zip(args.distro)

            step(5, total, "dual-platform catalog + self-check")
            build_catalog()

            step(6, total, "drop stale dev catalog cache")
            drop_stale_catalog_cache()

            step(7, total, "done")
    except (PipelineError, subprocess.TimeoutExpired) as exc:
        print(f"\nPIPELINE FAILED: {exc}", file=sys.stderr, flush=True)
        return 1

    elapsed = int(time.time() - started)
    print(
        "\n=== dual-platform build complete " + f"({elapsed // 60}m {elapsed % 60:02d}s) ===\n"
        f"win   : {WIN_ZIP}  ({WIN_ZIP.stat().st_size} bytes)\n"
        f"linux : {LINUX_ZIP}  ({LINUX_ZIP.stat().st_size} bytes)\n"
        f"catalog: {PKG_ROOT / 'dist-marketplace' / 'catalog.json'}\n"
        "\nNext steps:\n"
        "  - if the dev backend (28000) is running, refresh the marketplace catalog in the UI\n"
        "    (or restart the backend), then uninstall + reinstall the plugin to pick up the new package;\n"
        "  - optional: scripts/e2e-pi-web-plugin.py (Windows end-to-end)\n"
        "  - optional: wsl -d "
        f"{args.distro} -- bash {to_wsl_path(SCRIPT_DIR / 'wsl' / 'wsl-contract-test.sh')} (Linux contract)\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

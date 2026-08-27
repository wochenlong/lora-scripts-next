#!/usr/bin/env python3
"""Install musubi-tuner plugin environment without WebUI (CLI / portable)."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

UV_INSTALL_URL = "https://docs.astral.sh/uv/getting-started/installation/"


def _uv_bin_dir_candidates() -> list[Path]:
    """Dirs where `uv` may live next to the running interpreter (after pip install)."""
    base = Path(sys.executable).resolve().parent
    candidates = [base]
    if sys.platform == "win32":
        candidates.append(base / "Scripts")
    else:
        candidates.append(base / "bin")
        candidates.append(base.parent / "bin")
    return candidates


def _uv_exe_name() -> str:
    return "uv.exe" if sys.platform == "win32" else "uv"


def _prepend_path(directory: Path) -> None:
    os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")


def ensure_uv(log) -> str:
    """Return a usable `uv`, bootstrapping it via the current Python if missing."""
    found = shutil.which("uv")
    if found:
        return found

    for directory in _uv_bin_dir_candidates():
        exe = directory / _uv_exe_name()
        if exe.is_file():
            _prepend_path(directory)
            return str(exe)

    log("uv not found in PATH; bootstrapping it with the current Python ...")

    def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        log("  $ " + " ".join(cmd))
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

    if run([sys.executable, "-m", "pip", "--version"]).returncode != 0:
        if run([sys.executable, "-m", "ensurepip", "--upgrade"]).returncode != 0:
            raise SystemExit(
                "uv is required but not found, and pip could not be bootstrapped on this Python. "
                f"Install uv manually: {UV_INSTALL_URL}"
            )

    result = run([sys.executable, "-m", "pip", "install", "-U", "uv"])
    if result.returncode != 0:
        if result.stdout:
            log(result.stdout)
        if result.stderr:
            log(result.stderr)
        raise SystemExit(
            f"Failed to install uv via pip. Install uv manually: {UV_INSTALL_URL}"
        )

    for directory in _uv_bin_dir_candidates():
        exe = directory / _uv_exe_name()
        if exe.is_file():
            _prepend_path(directory)
            log(f"uv installed: {exe}")
            return str(exe)

    found = shutil.which("uv")
    if found:
        return found
    raise SystemExit(
        "uv was installed but could not be located on PATH. "
        f"Re-run the script, or install uv manually: {UV_INSTALL_URL}"
    )


def ensure_project_import_path(project_root: Path) -> None:
    root = str(project_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)


def find_project_root(start: Path | None = None) -> Path:
    candidates = [start or Path.cwd()]
    here = Path(__file__).resolve().parent
    candidates.append(here.parent.parent)
    for base in candidates:
        root = base.resolve()
        if (root / "gui.py").is_file() and (root / "mikazuki" / "engines" / "musubi").is_dir():
            return root
    raise SystemExit(
        "Cannot locate SD-Trainer project root (need gui.py and mikazuki/engines/musubi). "
        "Run from repo / SD-Trainer directory or pass --project-root."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install musubi-tuner plugin (extensions/musubi_tuner) for Krea 2 training."
    )
    parser.add_argument("--project-root", type=Path, default=None, help="SD-Trainer root (default: auto-detect)")
    parser.add_argument("--source-root", type=Path, default=None, help="Existing kohya-ss/musubi-tuner clone")
    parser.add_argument("--source-commit", default="", help="Pin upstream commit/tag")
    parser.add_argument("--cuda-extra", default="", help="Torch wheel flavor: cu124/cu128/cu130/cu132 (default: cu128)")
    parser.add_argument("--dry-run", action="store_true", help="Print install plan only")
    parser.add_argument("--pip-index-url", default="", help="PyPI index URL (default: https://pypi.org/simple)")
    parser.add_argument("--pytorch-index-url", default="", help="PyTorch wheel index base (cuda extra appended if missing)")
    parser.add_argument("--hf-endpoint", default="", help="Hugging Face endpoint (default: installer mirror)")
    parser.add_argument("--github-url-prefix", default="", help="GitHub URL prefix, e.g. https://ghfast.top/")
    args = parser.parse_args(argv)

    project_root = (args.project_root or find_project_root()).resolve()
    ensure_project_import_path(project_root)
    os.chdir(project_root)

    from mikazuki.engines.musubi.environment import build_environment_install_plan, install_environment, resolve_cuda_extra
    from mikazuki.engines.musubi.extension_state import default_layout, read_extension_status
    from mikazuki.engines.musubi.settings import feature_enabled, resolve_install_source_root
    from mikazuki.download_sources import parse_download_sources

    if not feature_enabled():
        raise SystemExit("musubi-tuner backend is disabled (LORA_ENABLE_MUSUBI=0).")

    commit = args.source_commit.strip() or None
    cuda_extra = args.cuda_extra.strip() or resolve_cuda_extra()
    download_sources = parse_download_sources(
        {
            "pip_index_url": args.pip_index_url,
            "pytorch_index_url": args.pytorch_index_url,
            "hf_endpoint": args.hf_endpoint,
            "github_url_prefix": args.github_url_prefix,
        }
    )
    try:
        source_root = resolve_install_source_root(project_root, args.source_root)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    layout = default_layout(project_root)
    plan = build_environment_install_plan(
        project_root,
        layout,
        source_root,
        dry_run=args.dry_run,
        source_commit=commit,
        cuda_extra=cuda_extra,
        download_sources=download_sources,
    )

    print(f"Project root : {project_root}")
    print(f"Source root  : {source_root}")
    print(f"Target source: {layout.source}")
    print(f"Venv python  : {layout.venv_python}")
    print(f"CUDA extra   : {cuda_extra}")
    if commit:
        print(f"Pin commit   : {commit}")

    if args.dry_run:
        print("[dry-run] No changes made.")
        return 0

    def log(line: str) -> None:
        print(line, flush=True)

    ensure_uv(log)

    result = install_environment(plan, log)
    status = read_extension_status(layout)
    print(f"Status: {status.state} ({status.reason})")
    if not result.ok:
        for err in result.errors:
            print(f"[error] {err}", file=sys.stderr)
        return 1
    print("")
    print("musubi-tuner plugin ready. Krea 2 LoRA training is available in the WebUI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Regression: batch passes %~dp0 with trailing backslash to PowerShell."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMON_PS1 = REPO_ROOT / "scripts" / "portable" / "portable_updater_common.ps1"


def _run_normalize(raw: str) -> str:
    cmd = (
        f". '{COMMON_PS1}'; "
        f"Normalize-PortableRootPath '{raw}'"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def test_portable_update_batch_templates_use_crlf() -> None:
    templates = REPO_ROOT / "build-scripts" / "templates"
    for name in ("Update-Next-Trainer-Release.bat", "Update-Next-Trainer.bat"):
        data = (templates / name).read_bytes()
        assert b"\r\n" in data, f"{name} must use CRLF for Windows cmd.exe"
        assert data.count(b"\n") == data.count(b"\r\n"), f"{name} must not use LF-only endings"


def test_portable_updater_ps1_files_have_utf8_bom() -> None:
    portable = REPO_ROOT / "scripts" / "portable"
    ps1_files = [
        "bootstrap_portable_updaters.ps1",
        "fix_portable_batch_crlf.ps1",
        "portable_updater_common.ps1",
        "show_portable_update_status.ps1",
        "update_from_release.ps1",
    ]
    for name in ps1_files:
        data = (portable / name).read_bytes()
        assert data.startswith(b"\xef\xbb\xbf"), f"{name} must start with UTF-8 BOM for PS 5.1"


def test_release_updater_uses_github_token_when_available() -> None:
    script = (
        REPO_ROOT / "scripts" / "portable" / "update_from_release.ps1"
    ).read_text(encoding="utf-8-sig")

    assert "$env:GITHUB_TOKEN" in script
    assert "$env:GH_TOKEN" in script
    assert '$headers["Authorization"] = "Bearer $githubToken"' in script


def test_normalize_strips_trailing_backslash_and_stray_quote() -> None:
    root = r"D:\pkg\SD-Trainer-v2.8.3"
    assert _run_normalize(root + "\\") == root
    assert _run_normalize(root + '\\"') == root


def test_update_from_release_dry_run_accepts_batch_style_path(tmp_path: Path) -> None:
    portable_root = tmp_path / "PortableRoot"
    trainer = portable_root / "Next-Trainer"
    trainer.mkdir(parents=True)
    (trainer / "gui.py").write_text("# stub\n", encoding="utf-8")

    ps1 = REPO_ROOT / "scripts" / "portable" / "update_from_release.ps1"
    batch_style = str(portable_root) + "\\\""
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps1),
            "-PortableRoot",
            batch_style,
            "-DryRun",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert "DryRun: release metadata reachable." in completed.stdout

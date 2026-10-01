import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts/portable/update_portable.py"


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args]).strip()


@pytest.fixture
def package(tmp_path, monkeypatch):
    for name in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv("GIT_" + name + "_NAME", "Portable test")
        monkeypatch.setenv("GIT_" + name + "_EMAIL", "test@example.invalid")
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-b", "dev")
    (source / "gui.py").write_text("old\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "initial")
    app = tmp_path / "pack" / "Next-Trainer"
    subprocess.run(["git", "clone", str(source), str(app)], check=True)
    (source / "gui.py").write_text("new\n")
    git(source, "commit", "-am", "update")
    return source, app


def worker():
    assert WORKER.exists(), "branch-aware worker is not implemented"
    return runpy.run_path(str(WORKER))


def test_dev_update_and_repeat_preserve_user_data(package):
    source, app = package
    data = app / "custom-dataset.txt"
    data.write_bytes(b"private")
    update = worker()["update"]
    update(app.parent)
    update(app.parent)
    assert git(app, "rev-parse", "HEAD") == git(source, "rev-parse", "HEAD")
    assert data.read_bytes() == b"private"
    assert git(app, "stash", "list") == b""
    assert git(app, "diff", "--name-only") == b""


def test_local_conflict_stops_without_modifying_data(package):
    source, app = package
    (app / "gui.py").write_bytes(b"user edit")
    old = git(app, "rev-parse", "HEAD")
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        worker()["update"](app.parent)
    assert git(app, "rev-parse", "HEAD") == old
    assert (app / "gui.py").read_bytes() == b"user edit"
    assert git(app, "stash", "list") == b""


def test_detached_head_does_not_fallback_to_main(package):
    _, app = package
    git(app, "checkout", "--detach")
    with pytest.raises(RuntimeError, match="branch"):
        worker()["update"](app.parent)


def test_fetch_failure_never_merges_stale_fetch_head(package):
    _, app = package
    git(app, "fetch", "origin", "dev")
    git(app, "remote", "set-url", "origin", str(app / "missing"))
    old = git(app, "rev-parse", "HEAD")
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        worker()["update"](app.parent)
    assert git(app, "rev-parse", "HEAD") == old


def test_concurrent_update_lock_does_not_change_head(package):
    _, app = package
    lock = app / ".git/portable-update.lock"
    lock.write_text("other process")
    old = git(app, "rev-parse", "HEAD")
    with pytest.raises(RuntimeError, match="Another update"):
        worker()["update"](app.parent)
    assert git(app, "rev-parse", "HEAD") == old
    assert lock.read_text() == "other process"


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_git_bootstrap_does_not_download_main_or_modify_checkout(package):
    _, app = package
    script = ROOT / "scripts/portable/bootstrap_portable_updaters.ps1"
    before = git(app, "status", "--porcelain")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(script), "-PortableRoot", str(app.parent)],
        capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert b"branch-local" in result.stdout
    assert git(app, "status", "--porcelain") == before


@pytest.mark.skipif(os.name != "nt", reason="Windows BAT")
def test_real_bat_can_replace_itself_and_repeat(package):
    source, app = package
    assert WORKER.exists(), "worker required before BAT integration"
    scripts = source / "scripts/portable"
    scripts.mkdir(parents=True)
    for name in ("update_portable.py", "portable_git.py"):
        (scripts / name).write_bytes((ROOT / "scripts/portable" / name).read_bytes())
    template = ROOT / "scripts/portable/templates/Update-Next-Trainer.bat"
    (scripts / "templates").mkdir()
    (scripts / "templates/Update-Next-Trainer.bat").write_bytes(template.read_bytes())
    git(source, "add", ".")
    git(source, "commit", "-m", "ship worker")
    git(app, "pull", "--ff-only")
    # Install a real root entry and create a newer target whose entry differs.
    root_bat = app.parent / "Update-Next-Trainer.bat"
    root_bat.write_bytes(template.read_bytes())
    (scripts / "templates/Update-Next-Trainer.bat").write_bytes(
        template.read_bytes() + b"\r\nrem New launcher revision\r\n")
    git(source, "commit", "-am", "change launcher")
    python_dir = app.parent / "python_embeded"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(python_dir), sys.base_prefix],
                   check=True, capture_output=True)
    try:
        for _ in range(2):
            result = subprocess.run(["cmd", "/d", "/c", str(root_bat), "--no-pause"],
                                    capture_output=True, timeout=60)
            assert result.returncode == 0, result.stdout + result.stderr
            assert b"not recognized" not in result.stdout + result.stderr
            assert git(app, "diff", "--name-only") == b""
        assert b"New launcher revision" in root_bat.read_bytes()
    finally:
        python_dir.rmdir()

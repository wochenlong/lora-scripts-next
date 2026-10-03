"""Branch-aware portable Git update; stdlib only, no online script overwrite."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()


@contextmanager
def update_lock(app):
    location = Path(git(app, "rev-parse", "--absolute-git-dir")) / "portable-update.lock"
    try:
        descriptor = os.open(location, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError(f"Another update may be running; inspect {location}") from None
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        yield
    finally:
        location.unlink()


def refresh_launchers(app, portable):
    files = {
        "run_gui.bat": "run_gui.bat",
        "scripts/portable/run_gui_portable_shim.bat": "run_gui_portable.bat",
        "scripts/portable/templates/Update-Next-Trainer.bat": "Update-Next-Trainer.bat",
        "scripts/portable/templates/Update-Next-Trainer-Release.bat": "Update-Next-Trainer-Release.bat",
    }
    for source, name in files.items():
        path = app / source
        if not path.is_file():
            continue
        if path.is_symlink() or (portable / name).is_symlink():
            raise RuntimeError(f"Refusing linked launcher: {name}")
        text = path.read_text(encoding="utf-8-sig")
        payload = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
        with tempfile.NamedTemporaryFile(dir=portable, delete=False) as stream:
            staged = Path(stream.name)
            stream.write(payload.encode("utf-8"))
        try:
            os.replace(staged, portable / name)
        finally:
            staged.unlink(missing_ok=True)


def update(portable):
    portable = Path(portable).resolve()
    app = portable / "Next-Trainer"
    branch = git(app, "branch", "--show-current")
    if not branch:
        raise RuntimeError("Select a local update branch; detached HEAD is not supported.")
    policy = app / "scripts/network_run.py"
    if policy.is_file():
        values = subprocess.check_output([sys.executable, "-s", str(policy), "--env-json"],
                                         cwd=app)
        os.environ.update({key: str(value) for key, value in json.loads(values).items()})
    # Load before Git changes the checkout; no imports from a half-updated tree.
    helper = runpy.run_path(str(Path(__file__).with_name("portable_git.py")))
    with update_lock(app):
        remote = git(app, "remote", "get-url", "origin")
        sources = [remote]
        if remote.startswith("https://github.com/"):
            sources += ["https://ghfast.top/" + remote, "https://mirror.ghproxy.com/" + remote]
        depth = ["--deepen=1000000"] if git(app, "rev-parse", "--is-shallow-repository") == "true" else []
        for source in sources:
            result = subprocess.run(
                ["git", "-C", str(app), "fetch", "--no-tags", *depth, "--",
                 source, f"refs/heads/{branch}"])
            if result.returncode == 0:
                break
        else:
            raise RuntimeError("Fetch failed; no application or updater files changed.")
        target = git(app, "rev-parse", "--verify", "FETCH_HEAD^{commit}")
        print(f"Updating {branch} to {target}", flush=True)
        helper["update"](app, target)
        refresh_launchers(app, portable)
    print("Update completed.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        update(args.portable_root)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Update stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

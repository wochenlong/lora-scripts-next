"""Git operations shared by the portable builder and updater (stdlib only)."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


DATA_PROBES = (
    "sd-models/portable-check.safetensors",
    "train/portable-check/image.png",
    "output/portable-check.safetensors",
    "logs/portable-check.log",
    "toml/autosave/portable-check.toml",
    "config/autosave/portable-check.toml",
)

BOOTSTRAP_FILES = (
    ".gitignore",
    ".gitattributes",
    "scripts/portable/portable_git.py",
    "scripts/portable/update_from_release.ps1",
    "scripts/portable/bootstrap_portable_updaters.ps1",
    "scripts/portable/show_portable_update_status.ps1",
    "scripts/portable/portable_updater_common.ps1",
    "scripts/portable/sync_portable_root_launchers.bat",
    "scripts/portable/UPDATER_VERSION",
    "scripts/portable/templates/Update-Next-Trainer.bat",
    "scripts/portable/templates/Update-Next-Trainer-Release.bat",
)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def verify(root):
    """Reject incomplete/modified tracked trees and exposed user data paths."""
    for name in (".gitignore", ".gitattributes"):
        if not (root / name).is_file():
            raise RuntimeError(f"Package is missing {name}")
    changes = git(root, "status", "--porcelain", "--untracked-files=no")
    if changes:
        raise RuntimeError(
            "Package tracked files differ from HEAD:\n"
            + changes.decode(errors="replace")
        )
    for path in DATA_PROBES:
        git(root, "check-ignore", "--no-index", "--quiet", "--", path)


def seed(source, destination):
    """Keep a complete shallow checkout, including dotfiles, at the build commit."""
    if destination.exists():
        raise RuntimeError(
            f"Build destination already exists: {destination}. Use -Clean."
        )
    if git(source, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError(
            "Commit tracked source/build output changes before packaging."
        )
    branch = git(source, "branch", "--show-current").decode().strip()
    if not branch:
        raise RuntimeError("Build from a branch, not a detached HEAD.")
    upstream = (
        git(
            source, "for-each-ref", "--format=%(upstream:short)", f"refs/heads/{branch}"
        )
        .decode()
        .strip()
    )
    update_branch = (
        upstream.removeprefix("origin/") if upstream.startswith("origin/") else branch
    )
    remote = git(source, "remote", "get-url", "origin").decode().strip()
    expected = git(source, "rev-parse", "HEAD").strip()
    subprocess.run(
        [
            "git",
            "clone",
            "--depth=1",
            "--single-branch",
            "--branch",
            branch,
            source.resolve().as_uri(),
            str(destination),
        ],
        check=True,
    )
    if git(destination, "rev-parse", "HEAD").strip() != expected:
        raise RuntimeError(
            "Source HEAD changed during the build snapshot. Retry with -Clean."
        )
    if update_branch != branch:
        git(destination, "branch", "-m", update_branch)
    git(destination, "remote", "set-url", "origin", remote)
    git(destination, "remote", "set-branches", "origin", update_branch)
    git(
        destination,
        "config",
        f"branch.{update_branch}.merge",
        f"refs/heads/{update_branch}",
    )
    verify(destination)


def update(root):
    root = root.resolve()
    # FETCH_HEAD is the result of the successful fetch, including mirror fetches.
    # Never stash/reset/clean: Git must refuse collisions, including ignored files.
    target = git(root, "rev-parse", "--verify", "FETCH_HEAD^{commit}").decode().strip()
    git(root, "merge-base", "--is-ancestor", "HEAD", target)
    # Extracted releases can have LF bytes with a CRLF checkout stat cache.
    # Re-add only content/mode-identical, unstaged files to refresh that cache;
    # real edits, deletions, and staged changes remain untouched.
    for raw_path in filter(None, git(root, "diff-files", "--name-only", "-z").split(b"\0")):
        path = os.fsdecode(raw_path)
        full = root / path
        if not full.is_file() or full.is_symlink():
            continue
        if git(root, "diff", "--cached", "--name-only", "--", path):
            continue
        if not git(root, "diff", "--no-ext-diff", "--no-textconv", "--name-only", "--", path):
            git(root, "add", "--", path)
    # Validate missing paths before merging, but do not restore old blobs yet:
    # historical CRLF blobs can appear dirty under the current text attributes.
    missing = git(root, "ls-files", "--deleted", "-z").split(b"\0")
    repair_paths = []
    for raw_path in filter(None, missing):
        path = os.fsdecode(raw_path)
        full = root / path
        if os.path.lexists(full):
            continue
        for parent in full.parents:
            if parent == root:
                break
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise RuntimeError(f"User file blocks missing program path: {path}")
        repair_paths.append(path)
    # Bootstrap downloads tracked scripts before the merge. Stage only files
    # already identical to the fetched commit, with no pre-existing staged edit.
    staged = []
    attributes_backup = None
    merged = False
    try:
        # Raw bootstrap BATs must match target CRLF blobs even when the old
        # attributes still normalize them to LF. Adopt only an untouched
        # attributes file, and roll it back if the merge cannot finish.
        attributes = root / ".gitattributes"
        entry = git(root, "ls-tree", target, "--", ".gitattributes").split()
        if (
            attributes.is_file()
            and not attributes.is_symlink()
            and len(entry) == 4
            and entry[0] in (b"100644", b"100755")
            and git(root, "ls-files", "--", ".gitattributes")
            and not git(root, "diff", "HEAD", "--name-only", "--", ".gitattributes")
            and not git(root, "diff", "--cached", "--name-only", "--", ".gitattributes")
            and git(root, "diff", "HEAD", target, "--name-only", "--", ".gitattributes")
        ):
            attributes_backup = attributes.read_bytes()
            git(root, "restore", f"--source={target}", "--worktree", "--", ".gitattributes")
        for path in BOOTSTRAP_FILES:
            if git(root, "diff", "--cached", "--name-only", "--", path):
                continue
            if git(root, "ls-files", "--", path):
                if not git(root, "diff", "--name-only", "--", path):
                    continue
                if git(root, "diff", target, "--name-only", "--", path):
                    continue
            else:
                # First bootstrap installs files absent from the old commit.
                # Only adopt regular allowlisted files matching the target blob.
                full = root / path
                if not full.is_file() or full.is_symlink():
                    continue
                entry = git(root, "ls-tree", target, "--", path).split()
                if len(entry) != 4 or entry[0] not in (b"100644", b"100755"):
                    continue
                if (
                    git(root, "hash-object", f"--path={path}", "--", path).strip()
                    != entry[2]
                ):
                    continue
            staged.append(path)
            git(root, "add", "--", path)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "merge.autostash=false",
                "merge",
                "--ff-only",
                "--no-autostash",
                "--no-overwrite-ignore",
                target,
            ],
            check=True,
        )
        merged = True
    finally:
        if staged:
            # On failure restore the original index; on success HEAD contains
            # exactly these files. Neither case writes to the working tree.
            git(root, "restore", "--staged", "--source=HEAD", "--", *staged)
        if attributes_backup is not None and not merged:
            attributes.write_bytes(attributes_backup)

    # Merge materializes changed files itself. Fill only paths still missing
    # from the new checkout, excluding files removed by the update.
    for path in repair_paths:
        if not os.path.lexists(root / path) and git(root, "ls-files", "--", path):
            git(root, "restore", "--worktree", "--", path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "verify", "update"))
    parser.add_argument("--trainer-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "seed":
            if args.source is None:
                parser.error("seed requires --source")
            seed(args.source, args.trainer_dir)
        elif args.action == "verify":
            verify(args.trainer_dir)
        else:
            update(args.trainer_dir)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Portable Git {args.action} stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

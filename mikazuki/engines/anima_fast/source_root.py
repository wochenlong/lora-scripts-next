from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from mikazuki.download_sources import apply_github_prefix
from mikazuki.engines.vendor_bundle import ensure_vendor_source, snapshot_matches

UPSTREAM_REPO = "https://github.com/sorryhyun/anima_lora.git"


class InstallSourceError(RuntimeError):
    """Anima Fast install cannot locate or prepare upstream source."""


def _has_train_py(path: Path) -> bool:
    return path.is_dir() and (path / "train.py").is_file()


def _is_git_checkout(path: Path) -> bool:
    return (path / ".git").is_dir()


def ensure_upstream_clone(
    project_root: Path,
    target: Path,
    commit: str | None,
    log: Callable[[str], None] | None = None,
    github_url_prefix: str | None = None,
) -> Path:
    target = target.resolve()
    if _has_train_py(target):
        if commit:
            subprocess.run(["git", "-C", str(target), "fetch", "origin", commit, "--depth", "1"], check=False)
            subprocess.run(["git", "-C", str(target), "checkout", commit], check=True)
        return target

    if target.exists() and any(target.iterdir()):
        raise InstallSourceError(f"Upstream cache exists but is not a valid anima_lora checkout: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    repo_url = apply_github_prefix(UPSTREAM_REPO, github_url_prefix)
    clone_cmd = ["git", "clone", "--depth", "1", repo_url, str(target)]
    if commit:
        clone_cmd = ["git", "clone", repo_url, str(target)]
    if log:
        log(f"[clone] {' '.join(clone_cmd)}")
    subprocess.run(clone_cmd, check=True)
    if commit:
        subprocess.run(["git", "-C", str(target), "checkout", commit], check=True)
    if not _has_train_py(target):
        raise InstallSourceError(f"Cloned upstream missing train.py: {target}")
    return target


def _usable_git_source(path: Path, source_commit: str | None) -> bool:
    if not _has_train_py(path):
        return False
    if source_commit and not _is_git_checkout(path):
        # A vendor-bundle snapshot carries the exact pinned tree without .git.
        return snapshot_matches(path, source_commit)
    return True


def default_upstream_cache(project_root: Path) -> Path:
    return (project_root / ".cache" / "anima_fast" / "upstream").resolve()


def resolve_install_source_root(
    project_root: Path,
    explicit: Path | str | None = None,
    source_commit: str | None = None,
    *,
    allow_clone: bool = False,
    log: Callable[[str], None] | None = None,
    github_url_prefix: str | None = None,
) -> Path:
    """Resolve sorryhyun/anima_lora source for Fast plugin install.

    Priority: explicit → ANIMA_LORA_ROOT → discover_runtime().anima_root →
    sibling ../anima_lora → vendor/anima_lora → .cache/anima_fast/upstream (clone when allowed).
    """
    project_root = project_root.resolve()
    commit = (source_commit or "").strip() or None

    if explicit is not None and str(explicit).strip():
        explicit_path = Path(explicit).resolve()
        if not _usable_git_source(explicit_path, commit):
            if not _has_train_py(explicit_path):
                raise InstallSourceError(f"Anima source root missing train.py: {explicit_path}")
            raise InstallSourceError(
                f"Anima source root must be a git checkout or pinned snapshot when source_commit is pinned: {explicit_path}"
            )
        return explicit_path

    env_root = os.environ.get("ANIMA_LORA_ROOT", "").strip()
    if env_root:
        env_path = Path(env_root).resolve()
        if _usable_git_source(env_path, commit):
            return env_path

    from .settings import discover_runtime

    runtime = discover_runtime(lora_next_root=project_root)
    commit = commit or runtime.source_commit
    installed_source = (project_root / "extensions" / "anima_lora" / "source").resolve()

    # Offline distribution: extract vendor/vendor-bundle.* once if present.
    ensure_vendor_source(project_root, "anima_lora", log=log)

    for candidate in (
        runtime.anima_root,
        (project_root.parent / "anima_lora").resolve(),
        (project_root / "vendor" / "anima_lora").resolve(),
    ):
        if candidate and candidate.resolve() != installed_source and _usable_git_source(candidate, commit):
            return candidate.resolve()

    cache_root = default_upstream_cache(project_root)
    if _usable_git_source(cache_root, commit):
        return cache_root

    if allow_clone:
        if not shutil.which("git"):
            raise InstallSourceError(
                "git is required to download Anima Fast source. Install Git or set ANIMA_LORA_ROOT "
                "to an existing sorryhyun/anima_lora clone."
            )
        return ensure_upstream_clone(
            project_root, cache_root, commit, log=log, github_url_prefix=github_url_prefix
        )

    return cache_root


def ensure_install_source_ready(
    project_root: Path,
    preferred: Path,
    source_commit: str | None,
    log: Callable[[str], None] | None = None,
    github_url_prefix: str | None = None,
) -> Path:
    preferred = preferred.resolve()
    commit = (source_commit or "").strip() or None
    if _usable_git_source(preferred, commit):
        return preferred
    return resolve_install_source_root(
        project_root,
        None,
        commit,
        allow_clone=True,
        log=log,
        github_url_prefix=github_url_prefix,
    )

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import shutil
import tarfile
import tempfile

from .extension_state import ExtensionLayout


EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "output",
    "image_dataset",
    "post_image_dataset",
    "_archive",
    "bench",
    "custom_nodes",
}

INCLUDE_TOP_LEVEL = {
    "train.py",
    "pyproject.toml",
    "uv.lock",
    "configs",
    "library",
    "networks",
    "preprocess",
    "scripts",
    "LICENSE",
    "NOTICE",
    "README.md",
}


@dataclass(frozen=True)
class InstallPlan:
    source_root: Path
    target_source: Path
    target_python: Path
    dry_run: bool = True
    source_commit: str | None = None

    def as_dict(self) -> dict:
        return {
            "source_root": str(self.source_root),
            "source_commit": self.source_commit,
            "target_source": str(self.target_source),
            "target_python": str(self.target_python),
            "dry_run": self.dry_run,
            "include": sorted(INCLUDE_TOP_LEVEL),
            "exclude_dirs": sorted(EXCLUDE_DIRS),
        }


def build_install_plan(
    source_root: Path,
    layout: ExtensionLayout,
    dry_run: bool = True,
    source_commit: str | None = None,
) -> InstallPlan:
    return InstallPlan(source_root.resolve(), layout.source.resolve(), layout.venv_python.resolve(), dry_run, source_commit)


def _ignore(_dir: str, names: list[str]) -> set[str]:
    return {name for name in names if name in EXCLUDE_DIRS}


def _git(source_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(source_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _existing_archive_paths(source_root: Path, commit: str) -> list[str]:
    paths: list[str] = []
    for name in sorted(INCLUDE_TOP_LEVEL):
        result = _git(source_root, ["ls-tree", "--name-only", commit, "--", name])
        if result.returncode == 0 and result.stdout.strip():
            paths.append(name)
    return paths


def _extract_git_archive(plan: InstallPlan, commit: str) -> None:
    resolved = _git(plan.source_root, ["rev-parse", "--verify", f"{commit}^{{commit}}"])
    if resolved.returncode != 0:
        raise ValueError(f"Anima source commit is not available in {plan.source_root}: {commit}")
    resolved_commit = resolved.stdout.strip()
    paths = _existing_archive_paths(plan.source_root, resolved_commit)
    if "train.py" not in paths:
        raise FileNotFoundError(f"Anima source commit is missing train.py: {resolved_commit}")
    if not paths:
        raise FileNotFoundError(f"Anima source commit has no installable runtime paths: {resolved_commit}")

    plan.target_source.parent.mkdir(parents=True, exist_ok=True)
    if plan.target_source.exists():
        shutil.rmtree(plan.target_source)
    plan.target_source.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        archive = Path(td) / "anima-source.tar"
        result = subprocess.run(
            ["git", "-C", str(plan.source_root), "archive", "--format=tar", "--output", str(archive), resolved_commit, "--", *paths],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(f"failed to archive Anima source commit {resolved_commit}: {result.stderr.strip()}")
        with tarfile.open(archive, "r") as tar:
            target = plan.target_source.resolve()
            for member in tar.getmembers():
                destination = (target / member.name).resolve()
                destination.relative_to(target)
            tar.extractall(target)
    (plan.target_source / ".source_commit").write_text(resolved_commit + "\n", encoding="utf-8")


def copy_source_snapshot(plan: InstallPlan) -> None:
    if plan.dry_run:
        return
    if not plan.source_root.is_dir():
        raise FileNotFoundError(f"Anima source root does not exist: {plan.source_root}")
    if plan.source_commit:
        _extract_git_archive(plan, plan.source_commit)
        return
    if not (plan.source_root / "train.py").is_file():
        raise FileNotFoundError(f"Anima source root is missing train.py: {plan.source_root}")
    plan.target_source.parent.mkdir(parents=True, exist_ok=True)
    if plan.target_source.exists():
        shutil.rmtree(plan.target_source)
    plan.target_source.mkdir(parents=True, exist_ok=True)
    for name in INCLUDE_TOP_LEVEL:
        src = plan.source_root / name
        if not src.exists():
            continue
        dst = plan.target_source / name
        if src.is_dir():
            shutil.copytree(src, dst, ignore=_ignore)
        else:
            shutil.copy2(src, dst)


def remove_extension(layout: ExtensionLayout, project_root: Path) -> None:
    target = layout.root.resolve()
    allowed_root = (project_root.resolve() / "extensions").resolve()
    try:
        target.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(f"refusing to remove path outside extensions: {target}") from exc
    if target.exists():
        shutil.rmtree(target)

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from .extension_state import ExtensionLayout


EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "output",
    "logs",
}

INCLUDE_TOP_LEVEL = {
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "src",
}


@dataclass(frozen=True)
class InstallPlan:
    source_root: Path
    target_source: Path
    target_python: Path
    dry_run: bool = True
    source_commit: str | None = None
    cuda_extra: str = "cu128"

    def as_dict(self) -> dict:
        return {
            "source_root": str(self.source_root),
            "source_commit": self.source_commit,
            "target_source": str(self.target_source),
            "target_python": str(self.target_python),
            "dry_run": self.dry_run,
            "cuda_extra": self.cuda_extra,
        }


def build_install_plan(
    source_root: Path,
    layout: ExtensionLayout,
    dry_run: bool = True,
    source_commit: str | None = None,
    cuda_extra: str = "cu128",
) -> InstallPlan:
    return InstallPlan(
        source_root.resolve(),
        layout.source.resolve(),
        layout.venv_python.resolve(),
        dry_run,
        source_commit,
        cuda_extra,
    )


def _ignore(_dir: str, names: list[str]) -> set[str]:
    return {name for name in names if name in EXCLUDE_DIRS}


def _top_level_scripts(source_root: Path) -> list[str]:
    """musubi entry points are thin wrappers at the repo root (krea2_train_network.py etc.)."""
    return sorted(path.name for path in source_root.glob("*.py"))


def _git(source_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(source_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _archive_paths(source_root: Path, commit: str) -> list[str]:
    names = sorted(INCLUDE_TOP_LEVEL)
    result = _git(source_root, ["ls-tree", "--name-only", commit])
    if result.returncode != 0:
        return []
    available = set(result.stdout.split())
    paths = [name for name in names if name in available]
    paths.extend(sorted(name for name in available if name.endswith(".py")))
    return paths


def _extract_git_archive(plan: InstallPlan, commit: str) -> None:
    resolved = _git(plan.source_root, ["rev-parse", "--verify", f"{commit}^{{commit}}"])
    if resolved.returncode != 0:
        raise ValueError(f"musubi-tuner source commit is not available in {plan.source_root}: {commit}")
    resolved_commit = resolved.stdout.strip()
    paths = _archive_paths(plan.source_root, resolved_commit)
    if "pyproject.toml" not in paths or "src" not in paths:
        raise FileNotFoundError(f"musubi-tuner source commit is missing pyproject.toml/src: {resolved_commit}")

    plan.target_source.parent.mkdir(parents=True, exist_ok=True)
    if plan.target_source.exists():
        shutil.rmtree(plan.target_source)
    plan.target_source.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        archive = Path(td) / "musubi-source.tar"
        result = subprocess.run(
            ["git", "-C", str(plan.source_root), "archive", "--format=tar", "--output", str(archive), resolved_commit, "--", *paths],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(f"failed to archive musubi-tuner source commit {resolved_commit}: {result.stderr.strip()}")
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
        raise FileNotFoundError(f"musubi-tuner source root does not exist: {plan.source_root}")
    if plan.source_commit:
        _extract_git_archive(plan, plan.source_commit)
        return
    if not (plan.source_root / "src" / "musubi_tuner").is_dir():
        raise FileNotFoundError(f"musubi-tuner source root is missing src/musubi_tuner: {plan.source_root}")
    plan.target_source.parent.mkdir(parents=True, exist_ok=True)
    if plan.target_source.exists():
        shutil.rmtree(plan.target_source)
    plan.target_source.mkdir(parents=True, exist_ok=True)
    for name in sorted(INCLUDE_TOP_LEVEL | set(_top_level_scripts(plan.source_root))):
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

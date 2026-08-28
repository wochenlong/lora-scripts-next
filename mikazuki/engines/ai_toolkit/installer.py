from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from .extension_state import ExtensionLayout
from mikazuki.engines.vendor_bundle import snapshot_commit, snapshot_matches


EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "output",
    "logs",
    "ui",
    "node_modules",
}

INCLUDE_TOP_LEVEL = {
    "run.py",
    # Imported by toolkit/metadata.py as a top-level module (`from info import ...`).
    "info.py",
    "version.py",
    "toolkit",
    "jobs",
    "extensions_built_in",
    "assets",
    "requirements.txt",
    "requirements_base.txt",
    "dgx_requirements.txt",
    "spark_requirements.txt",
    "README.md",
    "LICENSE",
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


def _git(source_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(source_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _archive_paths(source_root: Path, commit: str) -> list[str]:
    result = _git(source_root, ["ls-tree", "--name-only", commit])
    if result.returncode != 0:
        return []
    available = set(result.stdout.split())
    return [name for name in sorted(INCLUDE_TOP_LEVEL) if name in available]


def _extract_git_archive(plan: InstallPlan, commit: str) -> None:
    resolved = _git(plan.source_root, ["rev-parse", "--verify", f"{commit}^{{commit}}"])
    if resolved.returncode != 0:
        raise ValueError(f"ai-toolkit source commit is not available in {plan.source_root}: {commit}")
    resolved_commit = resolved.stdout.strip()
    paths = _archive_paths(plan.source_root, resolved_commit)
    if "run.py" not in paths or "toolkit" not in paths:
        raise FileNotFoundError(f"ai-toolkit source commit is missing run.py/toolkit: {resolved_commit}")

    plan.target_source.parent.mkdir(parents=True, exist_ok=True)
    if plan.target_source.exists():
        shutil.rmtree(plan.target_source)
    plan.target_source.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        archive = Path(td) / "ai-toolkit-source.tar"
        result = subprocess.run(
            ["git", "-C", str(plan.source_root), "archive", "--format=tar", "--output", str(archive), resolved_commit, "--", *paths],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(f"failed to archive ai-toolkit source commit {resolved_commit}: {result.stderr.strip()}")
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
        raise FileNotFoundError(f"ai-toolkit source root does not exist: {plan.source_root}")
    if plan.source_commit and not snapshot_matches(plan.source_root, plan.source_commit):
        _extract_git_archive(plan, plan.source_commit)
        return
    if not ((plan.source_root / "run.py").is_file() and (plan.source_root / "toolkit").is_dir()):
        raise FileNotFoundError(f"ai-toolkit source root is missing run.py/toolkit: {plan.source_root}")
    plan.target_source.parent.mkdir(parents=True, exist_ok=True)
    if plan.target_source.exists():
        shutil.rmtree(plan.target_source)
    plan.target_source.mkdir(parents=True, exist_ok=True)
    for name in sorted(INCLUDE_TOP_LEVEL):
        src = plan.source_root / name
        if not src.exists():
            continue
        dst = plan.target_source / name
        if src.is_dir():
            shutil.copytree(src, dst, ignore=_ignore)
        else:
            shutil.copy2(src, dst)
    # get_model.py iterates both extension roots; the snapshot ships no
    # third-party extensions but the directory must exist.
    (plan.target_source / "extensions").mkdir(exist_ok=True)
    if plan.source_commit:
        recorded = snapshot_commit(plan.source_root) or plan.source_commit
        (plan.target_source / ".source_commit").write_text(recorded + "\n", encoding="utf-8")
    elif snapshot_commit(plan.source_root):
        (plan.target_source / ".source_commit").write_text(
            snapshot_commit(plan.source_root) + "\n", encoding="utf-8"
        )


def remove_extension(layout: ExtensionLayout, project_root: Path) -> None:
    target = layout.root.resolve()
    allowed_root = (project_root.resolve() / "extensions").resolve()
    try:
        target.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(f"refusing to remove path outside extensions: {target}") from exc
    if target.exists():
        shutil.rmtree(target)

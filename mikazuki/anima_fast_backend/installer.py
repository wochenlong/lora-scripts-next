from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

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

    def as_dict(self) -> dict:
        return {
            "source_root": str(self.source_root),
            "target_source": str(self.target_source),
            "target_python": str(self.target_python),
            "dry_run": self.dry_run,
            "include": sorted(INCLUDE_TOP_LEVEL),
            "exclude_dirs": sorted(EXCLUDE_DIRS),
        }


def build_install_plan(source_root: Path, layout: ExtensionLayout, dry_run: bool = True) -> InstallPlan:
    return InstallPlan(source_root.resolve(), layout.source.resolve(), layout.venv_python.resolve(), dry_run)


def _ignore(_dir: str, names: list[str]) -> set[str]:
    return {name for name in names if name in EXCLUDE_DIRS}


def copy_source_snapshot(plan: InstallPlan) -> None:
    if plan.dry_run:
        return
    if not plan.source_root.is_dir():
        raise FileNotFoundError(f"Anima source root does not exist: {plan.source_root}")
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

"""Ensure portable user data lives under Next-Trainer/ (file picker cwd).

Canonical layout (v2.8.36+):
  <PortableRoot>/Next-Trainer/{sd-models,output,logs,train}/  — real folders
  <PortableRoot>/{sd-models,output,logs,train}/              — junctions -> above

Legacy layout (pre-#191 flip):
  data at portable root; Next-Trainer/<name> junction -> ../<name>
  Migrated on launch/build by moving data into Next-Trainer and reversing junctions.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# tagger-models stays at portable root (MIKAZUKI_TAGGER_MODELS_DIR).
TRAINER_CANONICAL_DIR_NAMES = (
    "sd-models",
    "output",
    "logs",
    "train",
)

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def resolve_portable_roots(trainer_dir: Path | None = None) -> tuple[Path, Path]:
    if trainer_dir is None:
        trainer_dir = Path.cwd()
    trainer_dir = trainer_dir.resolve()
    portable_root = trainer_dir.parent
    return trainer_dir, portable_root


def is_portable_layout(trainer_dir: Path, portable_root: Path) -> bool:
    if os.name != "nt":
        return False
    if (trainer_dir / "gui.py").is_file() and (portable_root / "python_embeded").is_dir():
        return True
    if (trainer_dir / "PORTABLE_BUILD").is_file():
        return True
    return False


def _is_reparse_point(path: Path) -> bool:
    try:
        attrs = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        return path.is_symlink()
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def _junction_target(link: Path) -> Path | None:
    if not _is_reparse_point(link):
        return None
    try:
        return link.resolve()
    except OSError:
        return None


def _create_junction(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=True,
        capture_output=True,
        text=True,
    )


def _remove_junction(link: Path) -> None:
    if _is_reparse_point(link):
        link.rmdir()


def _dir_entries(path: Path) -> list[Path]:
    if not path.is_dir() or _is_reparse_point(path):
        return []
    return list(path.iterdir())


def _path_or_reparse_exists(path: Path) -> bool:
    return path.exists() or _is_reparse_point(path)


def _conflict_destination(path: Path) -> Path:
    candidate = path.with_name(f"{path.name}.portable-root")
    index = 2
    while _path_or_reparse_exists(candidate):
        candidate = path.with_name(f"{path.name}.portable-root-{index}")
        index += 1
    return candidate


def _move_entries_preserving_conflicts(source: Path, destination: Path) -> None:
    for item in source.iterdir():
        target = destination / item.name
        if _path_or_reparse_exists(target):
            target = _conflict_destination(target)
        shutil.move(str(item), str(target))


def ensure_portable_data_dir(
    trainer_dir: Path,
    portable_root: Path,
    name: str,
    *,
    log=print,
) -> str:
    """
    Ensure trainer_dir/name is the real data folder; portable_root/name junctions to it.

    Returns: linked-outer | migrated-flip | migrated-outer-to-inner | skipped | failed
    """
    inner = trainer_dir / name
    outer = portable_root / name

    # --- Legacy: inner junction pointed at outer (data physically outside Next-Trainer) ---
    if _is_reparse_point(inner):
        existing_inner_tgt = _junction_target(inner)
        points_to_outer = (
            existing_inner_tgt is not None
            and existing_inner_tgt.resolve() == outer.resolve()
        )
        outer_is_real_dir = outer.is_dir() and not _is_reparse_point(outer)
        if points_to_outer or outer_is_real_dir:
            _remove_junction(inner)
            if outer_is_real_dir:
                if inner.exists():
                    shutil.rmtree(inner)
                shutil.move(str(outer), str(inner))
            else:
                inner.mkdir(parents=True, exist_ok=True)
            if _path_or_reparse_exists(outer):
                if _is_reparse_point(outer):
                    _remove_junction(outer)
                elif outer.is_dir():
                    shutil.rmtree(outer)
            _create_junction(outer, inner)
            log(f"[portable] migrated {name}: data now under Next-Trainer (root is junction)")
            return "migrated-flip"
        log(
            f"[portable] {name}: keep existing inner junction -> {existing_inner_tgt}; "
            "portable-root data folder is unavailable"
        )
        return "skipped"

    inner.mkdir(parents=True, exist_ok=True)

    # --- Outer real folder with data: merge into Next-Trainer without overwriting ---
    if outer.exists() and not _is_reparse_point(outer):
        outer_entries = _dir_entries(outer)
        if outer_entries:
            _move_entries_preserving_conflicts(outer, inner)
            shutil.rmtree(outer)
            _create_junction(outer, inner)
            log(f"[portable] migrated {name}: moved portable-root data into Next-Trainer")
            return "migrated-outer-to-inner"

    # --- Ensure outer junction -> inner ---
    if _is_reparse_point(outer):
        existing_outer_tgt = _junction_target(outer)
        if existing_outer_tgt is not None and existing_outer_tgt.resolve() == inner.resolve():
            return "skipped"
        _remove_junction(outer)
    elif outer.exists():
        if outer.is_dir() and not _dir_entries(outer):
            shutil.rmtree(outer)
        else:
            log(
                f"[portable] {name}: keep portable-root folder ({len(_dir_entries(outer))} item(s)); "
                f"file picker uses Next-Trainer\\{name}"
            )
            return "skipped"

    _create_junction(outer, inner)
    log(f"[portable] linked {outer} -> {inner}")
    return "linked-outer"


def link_portable_data_dir(
    trainer_dir: Path,
    portable_root: Path,
    name: str,
    *,
    log=print,
) -> str:
    """Backward-compatible alias."""
    return ensure_portable_data_dir(trainer_dir, portable_root, name, log=log)


def link_all_portable_data_dirs(
    trainer_dir: Path | None = None,
    *,
    log=print,
) -> dict[str, str]:
    trainer_dir, portable_root = resolve_portable_roots(trainer_dir)
    if not is_portable_layout(trainer_dir, portable_root):
        log("[portable] not a portable layout; skip data-dir layout")
        return {}

    results: dict[str, str] = {}
    for name in TRAINER_CANONICAL_DIR_NAMES:
        try:
            results[name] = ensure_portable_data_dir(
                trainer_dir,
                portable_root,
                name,
                log=log,
            )
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or exc.stdout or str(exc)).strip()
            log(f"[portable] failed to link {name}: {err}")
            results[name] = "failed"
        except OSError as exc:
            log(f"[portable] failed to link {name}: {exc}")
            results[name] = "failed"
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trainer-dir",
        type=Path,
        default=None,
        help="Next-Trainer directory (default: current working directory)",
    )
    args = parser.parse_args(argv)
    link_all_portable_data_dirs(args.trainer_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TAGGER_DIRS = (
    REPO_ROOT / "taggers",
    REPO_ROOT / "models" / "taggers",
    REPO_ROOT / "huggingface" / "taggers",
)


def iter_tagger_roots() -> list[Path]:
    roots: list[Path] = []
    env_value = os.environ.get("MIKAZUKI_TAGGER_DIR", "")
    for item in env_value.split(os.pathsep):
        if item.strip():
            roots.append(Path(item).expanduser().resolve())
    roots.extend(path.resolve() for path in DEFAULT_TAGGER_DIRS)
    return roots


def _candidate_file(model_dir: Path, relative_path: str) -> list[Path]:
    rel = Path(relative_path)
    return [
        model_dir / rel,
        model_dir / rel.name,
    ]


def resolve_local_tagger_files(model_key: str, required_files: list[str]) -> tuple[Path, ...] | None:
    for root in iter_tagger_roots():
        model_dirs = [root]
        if root.name != model_key:
            model_dirs.insert(0, root / model_key)

        for model_dir in model_dirs:
            resolved: list[Path] = []
            for required_file in required_files:
                found = next(
                    (candidate for candidate in _candidate_file(model_dir, required_file) if candidate.is_file()),
                    None,
                )
                if found is None:
                    break
                resolved.append(found)
            else:
                return tuple(resolved)

    return None

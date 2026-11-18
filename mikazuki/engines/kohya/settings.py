"""kohya (sd-scripts) runtime paths: an independent uv-managed interpreter + venv.

Unlike other packs the training source is not cloned into ``extensions/``:
sd-scripts ships with the repository (``vendor/sd-scripts`` + ``scripts/``)
and the venv only carries the interpreter and site-packages.
"""
from dataclasses import dataclass
from pathlib import Path
import sys

PYTHON_VERSION = "3.10"


def feature_enabled():
    return True


@dataclass(frozen=True)
class Runtime:
    project_root: Path

    @property
    def root(self):
        return self.project_root / "extensions" / "kohya"

    @property
    def python_install_dir(self):
        return self.root / ".python"

    @property
    def python(self):
        return self.root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    @property
    def state_file(self):
        return self.root / "install_state.json"


def main_env_python_candidates(project_root: Path):
    """Pre-standalone releases trained in the GUI's own ("main") environment:
    the portable pack's ``python_embeded`` next to ``Next-Trainer/``, or the
    interpreter running the GUI for source installs. Either may already hold a
    working torch stack and can serve as a fallback runtime.
    """
    candidates = []
    portable = project_root.parent / "python_embeded"
    for relative in ("python.exe", "python", "bin/python"):
        path = portable / relative
        if path.is_file():
            candidates.append(path)
    executable = Path(sys.executable)
    if executable.is_file():
        candidates.append(executable)
    unique = []
    seen = set()
    for path in candidates:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def runtime():
    return Runtime(Path.cwd().resolve())

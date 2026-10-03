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


def runtime():
    return Runtime(Path.cwd().resolve())

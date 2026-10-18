"""Isolated runtime layout for KohakuMossTrainer."""
from dataclasses import dataclass
from pathlib import Path
import os
import sys

from .manifest import FEATURE_FLAG_ENV

PYTHON_VERSION = "3.12"
TRAIN_SCRIPT = "scripts/train/moss.py"
PROJECT_ROOT_ENV = "NEXT_TRAINER_PROJECT_ROOT"


def feature_enabled() -> bool:
    return os.environ.get(FEATURE_FLAG_ENV, "1") != "0"


def default_project_root() -> Path:
    configured = os.environ.get(PROJECT_ROOT_ENV, "").strip()
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Runtime:
    project_root: Path

    @property
    def root(self) -> Path:
        return self.project_root / "extensions" / "kohaku-moss"

    @property
    def source(self) -> Path:
        return self.root / "source"

    @property
    def python_install_dir(self) -> Path:
        return self.root / ".python"

    @property
    def python(self) -> Path:
        return self.root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    @property
    def kogine(self) -> Path:
        return self.root / ".venv" / ("Scripts/kogine.exe" if sys.platform == "win32" else "bin/kogine")

    @property
    def state_file(self) -> Path:
        return self.root / "install_state.json"


def runtime(project_root=None) -> Runtime:
    return Runtime(Path(project_root or default_project_root()).expanduser().resolve())

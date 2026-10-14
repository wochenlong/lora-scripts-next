from dataclasses import dataclass
from pathlib import Path
import os
import sys

from .manifest import FEATURE_FLAG_ENV

TRAIN_SCRIPT = "examples/qwen_image_21/model_training/train.py"
PYTHON_VERSION = "3.12"
PROJECT_ROOT_ENV = "NEXT_TRAINER_PROJECT_ROOT"


def feature_enabled():
    return os.environ.get(FEATURE_FLAG_ENV, "1") != "0"


def default_project_root() -> Path:
    """Locate the Next Trainer repo root without relying on process cwd (#459).

    Prefer ``NEXT_TRAINER_PROJECT_ROOT`` when a launcher sets it; otherwise walk
    up from this package (``mikazuki/engines/diffsynth`` → repo root).
    """
    configured = os.environ.get(PROJECT_ROOT_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Runtime:
    project_root: Path

    @property
    def root(self):
        return self.project_root / "extensions" / "diffsynth"

    @property
    def source(self):
        return self.root / "source"

    @property
    def python_install_dir(self):
        return self.root / ".python"

    @property
    def python(self):
        return self.root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    @property
    def state_file(self):
        return self.root / "install_state.json"


def runtime(project_root: Path | None = None):
    return Runtime((project_root or default_project_root()).resolve())

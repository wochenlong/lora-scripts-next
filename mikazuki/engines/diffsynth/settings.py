from dataclasses import dataclass
from pathlib import Path
import os
import sys

from .manifest import FEATURE_FLAG_ENV

TRAIN_SCRIPT = "examples/qwen_image_21/model_training/train.py"
PYTHON_VERSION = "3.12"


def feature_enabled():
    return os.environ.get(FEATURE_FLAG_ENV, "1") != "0"


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


def runtime():
    return Runtime(Path.cwd().resolve())

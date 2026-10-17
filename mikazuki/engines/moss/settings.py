"""The engine owns its source, interpreter, venv, and installation state."""
from dataclasses import dataclass
from pathlib import Path
import os
import sys

from .manifest import FEATURE_FLAG_ENV

PYTHON_VERSION = "3.13"
PROJECT_ROOT_ENV = "NEXT_TRAINER_PROJECT_ROOT"
TRAIN_SCRIPT = "scripts/moss/train.py"
CACHE_SCRIPT = "scripts/moss/cache.py"
REQUIRED_SOURCE_FILES = (
    "pyproject.toml", "library/env.py", "library/downloads.py",
    "library/moss/requests.py", "library/moss/model.py", "library/moss/loader.py",
    "library/moss/train.py", "library/moss/cache.py", "library/moss/lora.py",
    "library/moss/scan.py", "library/qwen21/blockswap.py",
    "library/runtime/offloading.py", "library/runtime/device.py", "library/runtime/dynamo.py",
    TRAIN_SCRIPT, CACHE_SCRIPT,
)


def feature_enabled():
    return os.environ.get(FEATURE_FLAG_ENV, "1") != "0"


def default_project_root():
    configured = os.environ.get(PROJECT_ROOT_ENV, "").strip()
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Runtime:
    project_root: Path

    @property
    def root(self):
        return self.project_root / "extensions" / "moss"

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


def runtime(project_root=None):
    return Runtime(Path(project_root or default_project_root()).expanduser().resolve())

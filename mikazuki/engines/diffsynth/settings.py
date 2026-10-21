from dataclasses import dataclass
from pathlib import Path
import os
import sys

from .manifest import FEATURE_FLAG_ENV

TRAIN_SCRIPT = "examples/qwen_image_21/model_training/train.py"
PYTHON_VERSION = "3.12"
PROJECT_ROOT_ENV = "NEXT_TRAINER_PROJECT_ROOT"
CACHE_DIR_ENV = "NEXT_DIFFSYNTH_CACHE_DIR"


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


def remember_cache_dir(override: str) -> None:
    raw = str(override or "").strip()
    if not raw:
        return
    from mikazuki.user_data import UserDataError, UserDataStore
    store = UserDataStore()
    try:
        settings = store.read_settings()
        if str(settings.get("paths", {}).get("diffsynth_cache") or "") == raw:
            return
        store.patch_settings({"paths": {"diffsynth_cache": raw}}, settings["revision"])
    except (UserDataError, OSError):
        return


def configured_cache_dir(rt: Runtime, override: str = "") -> Path:
    for raw in (str(override or "").strip(), os.environ.get(CACHE_DIR_ENV, "").strip()):
        if raw:
            path = Path(raw).expanduser()
            return path.resolve() if path.is_absolute() else (rt.project_root / path).resolve()
    from mikazuki.user_data import UserDataStore
    raw = str(UserDataStore().read_settings().get("paths", {}).get("diffsynth_cache") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        return path.resolve() if path.is_absolute() else (rt.project_root / path).resolve()
    return rt.root / "cache" / "models"

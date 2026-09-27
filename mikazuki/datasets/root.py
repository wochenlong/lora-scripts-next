from pathlib import Path

from mikazuki.app.config import app_config

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASETS_ROOT = "./datasets"
CONFIG_KEY = "datasets_root"


def normalize_path(path: str | Path) -> str:
    return str(Path(path).resolve()).replace("\\", "/")


def resolve_root(raw: str) -> Path:
    path = Path(raw.strip()).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def get_datasets_root() -> Path:
    raw = app_config[CONFIG_KEY] or DEFAULT_DATASETS_ROOT
    return resolve_root(raw)


def set_datasets_root(raw: str) -> Path:
    if not raw or not raw.strip():
        raise ValueError("datasets root path is empty")
    resolved = resolve_root(raw)
    resolved.mkdir(parents=True, exist_ok=True)
    app_config[CONFIG_KEY] = raw.strip()
    app_config.save_config()
    return resolved

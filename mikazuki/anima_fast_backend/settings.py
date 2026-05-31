from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 runtime
    import toml as tomllib


DEFAULT_CONFIG = Path("config/anima_fast_backend.toml")


@dataclass(frozen=True)
class RuntimeConfig:
    anima_root: Path
    python: Path
    lora_next_root: Path
    output_dir: Path
    logging_dir: Path
    cache_dir: Path
    hf_home: Path | None = None
    preflight_level: str = "full"
    allow_unsupported: bool = False
    source_commit: str | None = None


def _as_path(value: str | os.PathLike | None, base: Path) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def repo_root() -> Path:
    return Path.cwd().resolve()


def load_backend_config(root: Path | None = None) -> dict:
    root = (root or repo_root()).resolve()
    path = root / DEFAULT_CONFIG
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def feature_kill_switch(env: dict[str, str] | None = None, config: dict | None = None) -> bool:
    """Maintainer-only emergency off switch. Default: Fast UI stays visible."""
    env = env or os.environ
    config = config or load_backend_config()
    key = config.get("features", {}).get("enabled_env", "LORA_ENABLE_ANIMA_FAST")
    raw = str(env.get(key, "")).strip().lower()
    if not raw:
        return False
    return raw in {"0", "false", "no", "off"}


def feature_enabled(env: dict[str, str] | None = None, config: dict | None = None) -> bool:
    return not feature_kill_switch(env=env, config=config)


def dev_mode_enabled(env: dict[str, str] | None = None, config: dict | None = None) -> bool:
    env = env or os.environ
    config = config or load_backend_config()
    key = config.get("features", {}).get("dev_mode_env", "LORA_ANIMA_FAST_DEV_MODE")
    return _truthy(env.get(key, "0"))


def discover_runtime(config: dict | None = None, lora_next_root: Path | None = None) -> RuntimeConfig:
    lora_next_root = (lora_next_root or repo_root()).resolve()
    config = config or load_backend_config(lora_next_root)
    backend = config.get("backend", {})
    paths = config.get("paths", {})

    extension_source = _as_path(backend.get("source_dir"), lora_next_root)
    extension_python = _as_path(backend.get("venv_python"), lora_next_root)
    external_root = _as_path(backend.get("external_root"), lora_next_root)
    external_python = _as_path(backend.get("external_python"), lora_next_root)

    root = (
        (extension_source if extension_source and (extension_source / "train.py").is_file() else None)
        or _as_path(os.environ.get("ANIMA_LORA_ROOT"), lora_next_root)
        or external_root
        or (lora_next_root.parent / "anima_lora").resolve()
    )
    python = (
        _as_path(os.environ.get("ANIMA_LORA_PYTHON"), lora_next_root)
        or (extension_python if extension_python and extension_python.is_file() else None)
        or external_python
        or (root / ".venv" / "Scripts" / "python.exe").resolve()
    )

    return RuntimeConfig(
        anima_root=root,
        python=python,
        lora_next_root=lora_next_root,
        output_dir=(_as_path(paths.get("output_dir"), lora_next_root) or (lora_next_root / "output" / "anima_fast")).resolve(),
        logging_dir=(_as_path(paths.get("logging_dir"), lora_next_root) or (lora_next_root / "logs" / "anima_fast")).resolve(),
        cache_dir=(_as_path(paths.get("cache_dir"), lora_next_root) or (lora_next_root / ".cache" / "anima_fast")).resolve(),
        hf_home=_as_path(backend.get("hf_home"), lora_next_root),
        preflight_level=str(backend.get("preflight_level", "full")),
        allow_unsupported=_truthy(backend.get("allow_unsupported", False)),
        source_commit=str(backend.get("source_commit") or "").strip() or None,
    )

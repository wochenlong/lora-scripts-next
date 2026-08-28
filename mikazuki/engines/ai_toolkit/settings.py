from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 runtime
    import toml as tomllib

from mikazuki.download_sources import apply_github_prefix
from mikazuki.engines.vendor_bundle import ensure_vendor_source, snapshot_matches


DEFAULT_CONFIG = Path("config/ai_toolkit_backend.toml")
UPSTREAM_REPO = "https://github.com/ostris/ai-toolkit.git"


@dataclass(frozen=True)
class RuntimeConfig:
    toolkit_root: Path
    python: Path
    lora_next_root: Path
    output_dir: Path
    logging_dir: Path
    cache_dir: Path
    hf_home: Path | None = None


def _as_path(value: str | os.PathLike | None, base: Path) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _venv_python_for_root(root: Path) -> Path:
    if sys.platform == "win32":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def repo_root() -> Path:
    return Path.cwd().resolve()


def load_backend_config(root: Path | None = None) -> dict:
    root = (root or repo_root()).resolve()
    path = root / DEFAULT_CONFIG
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def feature_kill_switch(env: dict[str, str] | None = None, config: dict | None = None) -> bool:
    """Maintainer-only emergency off switch. Default: ai-toolkit backend stays visible."""
    env = env or os.environ
    config = config or load_backend_config()
    key = config.get("features", {}).get("enabled_env", "LORA_ENABLE_AI_TOOLKIT")
    raw = str(env.get(key, "")).strip().lower()
    if not raw:
        return False
    return raw in {"0", "false", "no", "off"}


def feature_enabled(env: dict[str, str] | None = None, config: dict | None = None) -> bool:
    return not feature_kill_switch(env=env, config=config)


def _has_package_tree(path: Path) -> bool:
    return (path / "run.py").is_file() and (path / "toolkit").is_dir()


def default_upstream_cache(project_root: Path) -> Path:
    return (project_root / ".cache" / "ai-toolkit" / "upstream").resolve()


def ensure_upstream_clone(
    project_root: Path,
    target: Path,
    commit: str | None,
    log: Callable[[str], None] | None = None,
    github_url_prefix: str | None = None,
) -> Path:
    target = target.resolve()
    if _has_package_tree(target):
        if commit:
            subprocess.run(["git", "-C", str(target), "fetch", "origin", commit, "--depth", "1"], check=False)
            subprocess.run(["git", "-C", str(target), "checkout", commit], check=True)
        return target
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"ai-toolkit 上游缓存已存在但不是有效源码目录: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    repo_url = apply_github_prefix(UPSTREAM_REPO, github_url_prefix)
    clone_cmd = ["git", "clone", "--depth", "1", repo_url, str(target)]
    if commit:
        clone_cmd = ["git", "clone", repo_url, str(target)]
    if log:
        log(f"[clone] {' '.join(clone_cmd)}")
    subprocess.run(clone_cmd, check=True)
    if commit:
        subprocess.run(["git", "-C", str(target), "checkout", commit], check=True)
    if not _has_package_tree(target):
        raise ValueError(f"克隆的 ai-toolkit 缺少 run.py/toolkit: {target}")
    return target


def _commit_available(path: Path, commit: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
        capture_output=True,
    )
    return result.returncode == 0


def _usable_source(path: Path, commit: str | None) -> bool:
    """Package tree +, when a commit is pinned, either a git checkout that
    actually has the commit or a snapshot whose .source_commit matches."""
    if not _has_package_tree(path):
        return False
    if not commit:
        return True
    if not (path / ".git").exists():
        return snapshot_matches(path, commit)
    return _commit_available(path, commit)


def resolve_install_source_root(
    project_root: Path,
    explicit: Path | None = None,
    source_commit: str | None = None,
    *,
    allow_clone: bool = False,
    log: Callable[[str], None] | None = None,
    github_url_prefix: str | None = None,
) -> Path:
    """Locate an ai-toolkit source checkout usable as install input.

    Priority: explicit → AI_TOOLKIT_ROOT → vendor/ai-toolkit →
    .cache/ai-toolkit/upstream (git clone when allow_clone is set).
    """
    commit = (source_commit or "").strip() or None
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit if explicit.is_absolute() else (project_root / explicit))
    env_root = os.environ.get("AI_TOOLKIT_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    ensure_vendor_source(project_root, "ai-toolkit", log=log)
    candidates.append(project_root / "vendor" / "ai-toolkit")
    for candidate in candidates:
        if _usable_source(candidate, commit):
            return candidate.resolve()
    cache_root = default_upstream_cache(project_root)
    if _has_package_tree(cache_root) and (cache_root / ".git").exists() and commit and not _commit_available(cache_root, commit):
        if allow_clone:
            return ensure_upstream_clone(project_root, cache_root, commit, log=log, github_url_prefix=github_url_prefix)
    elif _usable_source(cache_root, commit):
        return cache_root
    if allow_clone:
        if not shutil.which("git"):
            raise ValueError(
                "需要 git 才能自动下载 ai-toolkit 源码。请安装 git，"
                "或设置 AI_TOOLKIT_ROOT 指向现有的 ostris/ai-toolkit 克隆。"
            )
        return ensure_upstream_clone(
            project_root,
            cache_root,
            commit,
            log=log,
            github_url_prefix=github_url_prefix,
        )
    searched = ", ".join(str(c) for c in [*candidates, cache_root])
    raise ValueError(
        "未找到 ai-toolkit 源码。请先把 https://github.com/ostris/ai-toolkit "
        f"克隆到 vendor/ai-toolkit（或设置 AI_TOOLKIT_ROOT）。已查找: {searched}"
    )


def ensure_install_source_ready(
    project_root: Path,
    preferred: Path,
    source_commit: str | None = None,
    log: Callable[[str], None] | None = None,
    github_url_prefix: str | None = None,
) -> Path:
    preferred = preferred.resolve()
    if _usable_source(preferred, (source_commit or "").strip() or None):
        return preferred
    return resolve_install_source_root(
        project_root,
        None,
        source_commit,
        allow_clone=True,
        log=log,
        github_url_prefix=github_url_prefix,
    )


def discover_runtime(config: dict | None = None, lora_next_root: Path | None = None) -> RuntimeConfig:
    from .extension_state import default_layout

    lora_next_root = (lora_next_root or repo_root()).resolve()
    config = config or load_backend_config(lora_next_root)
    backend = config.get("backend", {})
    paths = config.get("paths", {})
    layout = default_layout(lora_next_root)

    config_root = _as_path(backend.get("source_dir"), lora_next_root)
    env_root = _as_path(os.environ.get("AI_TOOLKIT_ROOT"), lora_next_root)
    root = (
        (config_root if config_root and _has_package_tree(config_root) else None)
        or (env_root if env_root and _has_package_tree(env_root) else None)
        or (layout.source if _has_package_tree(layout.source) else None)
        or (lora_next_root / "vendor" / "ai-toolkit").resolve()
    )
    config_python = _as_path(backend.get("venv_python"), lora_next_root)
    env_python = _as_path(os.environ.get("AI_TOOLKIT_PYTHON"), lora_next_root)
    python = (
        (config_python if config_python and config_python.is_file() else None)
        or (env_python if env_python and env_python.is_file() else None)
        or (layout.venv_python if root.resolve() == layout.source.resolve() else _venv_python_for_root(root))
    )

    return RuntimeConfig(
        toolkit_root=root,
        python=python,
        lora_next_root=lora_next_root,
        output_dir=(_as_path(paths.get("output_dir"), lora_next_root) or (lora_next_root / "output" / "ai-toolkit")).resolve(),
        logging_dir=(_as_path(paths.get("logging_dir"), lora_next_root) or (lora_next_root / "logs" / "ai-toolkit")).resolve(),
        cache_dir=(_as_path(paths.get("cache_dir"), lora_next_root) or (lora_next_root / ".cache" / "ai-toolkit")).resolve(),
        hf_home=_as_path(backend.get("hf_home"), lora_next_root),
    )

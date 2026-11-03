"""Resolved download mirrors for engine installs (Fast / Musubi).

Source settings persist on the backend (``config/download-sources.local.json``)
and apply to every install regardless of which client triggers it. Explicit
payload fields still win for one-off overrides; when neither the payload nor a
saved config provides a field, installers keep their previous defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any


_CU_SUFFIX = re.compile(r"/cu\d+$", re.IGNORECASE)


@dataclass(frozen=True)
class DownloadSources:
    pip_index_url: str | None = None
    pytorch_index_url: str | None = None
    hf_endpoint: str | None = None
    github_url_prefix: str | None = None
    proxy_url: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        from mikazuki.networking import redact
        return {
            "pip_index_url": redact(self.pip_index_url) if self.pip_index_url else None,
            "pytorch_index_url": redact(self.pytorch_index_url) if self.pytorch_index_url else None,
            "hf_endpoint": redact(self.hf_endpoint) if self.hf_endpoint else None,
            "github_url_prefix": redact(self.github_url_prefix) if self.github_url_prefix else None,
            "proxy_url": redact(self.proxy_url) if self.proxy_url else None,
        }


def _nonempty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_download_sources(payload: dict | None) -> DownloadSources | None:
    """Parse install/repair JSON body (flat fields or nested ``download_sources``)."""
    if not isinstance(payload, dict):
        return None
    nested = payload.get("download_sources")
    data = nested if isinstance(nested, dict) else payload
    return _sources_from_mapping(data)


def _sources_from_mapping(data: dict) -> DownloadSources | None:
    if not isinstance(data, dict):
        return None
    sources = DownloadSources(
        pip_index_url=_nonempty(data.get("pip_index_url")),
        pytorch_index_url=_nonempty(data.get("pytorch_index_url")),
        hf_endpoint=_nonempty(data.get("hf_endpoint")),
        github_url_prefix=_nonempty(data.get("github_url_prefix")),
        proxy_url=_nonempty(data.get("proxy_url")),
    )
    if not any(sources.as_dict().values()):
        return None
    return sources


def config_path() -> Path:
    return Path(os.environ.get("NEXT_TRAINER_DOWNLOAD_SOURCES_CONFIG", "config/download-sources.local.json"))


def load_download_sources() -> DownloadSources | None:
    """Read the persisted server-side config; missing/invalid file → None."""
    path = config_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError(f"下载源配置文件无效，请修复 {path}。") from None
    return _sources_from_mapping(data)


def save_download_sources(sources: DownloadSources | None) -> None:
    """Persist the server-side config; None / all-auto removes the file."""
    path = config_path()
    if sources is None:
        path.unlink(missing_ok=True)
        return
    payload = {
        key: value
        for key, value in {
            "pip_index_url": sources.pip_index_url,
            "pytorch_index_url": sources.pytorch_index_url,
            "hf_endpoint": sources.hf_endpoint,
            "github_url_prefix": sources.github_url_prefix,
            "proxy_url": sources.proxy_url,
        }.items()
        if value
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_download_sources(payload: dict | None) -> DownloadSources | None:
    """Payload fields win; otherwise fall back to the persisted server config.

    Neither present → None, so installers keep their built-in defaults and
    CLI / older clients behave exactly as before any config was saved.
    """
    return parse_download_sources(payload) or load_download_sources()


def apply_github_prefix(url: str, prefix: str | None) -> str:
    """Prefix GitHub HTTPS URLs the same way as the portable updater (ghfast / ghproxy)."""
    cleaned = (prefix or "").strip()
    if not cleaned:
        return url
    if not cleaned.endswith("/"):
        cleaned += "/"
    if url.startswith(cleaned):
        return url
    return cleaned + url


def pytorch_extra_index_url(base: str | None, cuda_tag: str, default_full: str) -> str:
    """Build ``--extra-index-url``; append ``/cuXXX`` when the base has no CUDA suffix."""
    if not base:
        return default_full
    trimmed = base.rstrip("/")
    if _CU_SUFFIX.search(trimmed):
        return trimmed
    tag = (cuda_tag or "").strip().lstrip("/")
    if not tag:
        return trimmed
    return f"{trimmed}/{tag}"


def install_process_env(sources: DownloadSources | None) -> dict[str, str]:
    """Explicit process network policy; no host-environment mutation."""
    from mikazuki.networking import resolve_policy
    env = resolve_policy().process_env()
    # Include empty aliases so legacy callers merging into os.environ cannot
    # reintroduce a proxy disabled by direct mode.
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        env.setdefault(key, "")
        env.setdefault(key.lower(), env[key])
    if sources and sources.hf_endpoint:
        env["HF_ENDPOINT"] = sources.hf_endpoint
    if sources and sources.proxy_url:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env[key] = sources.proxy_url
    return env

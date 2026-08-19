"""Resolved download mirrors for engine installs (Fast / Musubi).

Frontend sends absolute URLs from Settings → Engines download-source prefs.
CLI / older clients may omit them; installers then keep their previous defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_CU_SUFFIX = re.compile(r"/cu\d+$", re.IGNORECASE)


@dataclass(frozen=True)
class DownloadSources:
    pip_index_url: str | None = None
    pytorch_index_url: str | None = None
    hf_endpoint: str | None = None
    github_url_prefix: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "pip_index_url": self.pip_index_url,
            "pytorch_index_url": self.pytorch_index_url,
            "hf_endpoint": self.hf_endpoint,
            "github_url_prefix": self.github_url_prefix,
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
    sources = DownloadSources(
        pip_index_url=_nonempty(data.get("pip_index_url")),
        pytorch_index_url=_nonempty(data.get("pytorch_index_url")),
        hf_endpoint=_nonempty(data.get("hf_endpoint")),
        github_url_prefix=_nonempty(data.get("github_url_prefix")),
    )
    if not any(sources.as_dict().values()):
        return None
    return sources


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


def install_process_env(sources: DownloadSources | None) -> dict[str, str] | None:
    """Env overrides for install subprocesses (currently HF_ENDPOINT only)."""
    if sources is None or not sources.hf_endpoint:
        return None
    return {"HF_ENDPOINT": sources.hf_endpoint}

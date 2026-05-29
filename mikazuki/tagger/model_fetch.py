"""Download interrogator assets from Hugging Face with progress reporting."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator

from huggingface_hub import hf_hub_download, try_to_load_from_cache

from mikazuki.tagger.local_models import asset_filenames, local_model_asset_paths
from mikazuki.tagger.progress import TaggerCancelled, tagger_progress

if TYPE_CHECKING:
    from mikazuki.tagger.interrogators.base import Interrogator


def _asset_filenames(interrogator: "Interrogator") -> list[str]:
    return asset_filenames(interrogator)


def _hf_kwargs(interrogator: "Interrogator") -> dict:
    kwargs = dict(getattr(interrogator, "kwargs", {}) or {})
    if not kwargs.get("repo_id"):
        raise ValueError("interrogator 未配置 Hugging Face repo_id")
    return kwargs


def _file_cached(kwargs: dict, filename: str) -> bool:
    revision = kwargs.get("revision")
    repo_id = kwargs["repo_id"]
    cached = try_to_load_from_cache(
        repo_id=repo_id,
        filename=filename,
        revision=revision,
    )
    if cached is not None:
        return True
    try:
        hf_hub_download(**kwargs, filename=filename, local_files_only=True)
        return True
    except Exception:
        return False


def interrogator_assets_ready(interrogator: "Interrogator", model_key: str | None = None) -> bool:
    """Return True when all HF files for this interrogator are already in the local cache."""
    if model_key and local_model_asset_paths(model_key, interrogator):
        return True
    kwargs = _hf_kwargs(interrogator)
    files = _asset_filenames(interrogator)
    if not files:
        return False
    return all(_file_cached(kwargs, filename) for filename in files)


def _hf_tqdm_module():
    """Return the real tqdm submodule (not the tqdm class re-exported by `import ...tqdm`)."""
    import huggingface_hub.utils  # noqa: F401 — ensure submodule is loaded

    return sys.modules["huggingface_hub.utils.tqdm"]


def _hf_tqdm_class():
    return _hf_tqdm_module().tqdm


class _TaggerDownloadTqdm(_hf_tqdm_class()):
    """Bridge Hugging Face hub tqdm bytes to tagger_progress API."""

    _file_index: int = 1
    _file_total: int = 1
    _filename: str = ""

    def update(self, n=1):
        if tagger_progress.is_cancel_requested():
            raise TaggerCancelled()
        result = super().update(n)
        total = int(getattr(self, "total", 0) or 0)
        current = int(getattr(self, "n", 0) or 0)
        tagger_progress.set_download_bytes(
            file_index=self._file_index,
            file_total=self._file_total,
            filename=self._filename,
            bytes_current=current,
            bytes_total=total,
        )
        return result


@contextmanager
def _hub_download_progress(file_index: int, file_total: int, filename: str) -> Iterator[None]:
    import huggingface_hub.utils as hf_utils

    class _BoundTaggerDownloadTqdm(_TaggerDownloadTqdm):
        _file_index = file_index
        _file_total = file_total
        _filename = filename

    hf_tqdm_module = _hf_tqdm_module()
    originals = {
        "module": hf_tqdm_module.tqdm,
        "utils": hf_utils.tqdm,
    }
    hf_tqdm_module.tqdm = _BoundTaggerDownloadTqdm
    hf_utils.tqdm = _BoundTaggerDownloadTqdm
    try:
        yield
    finally:
        hf_tqdm_module.tqdm = originals["module"]
        hf_utils.tqdm = originals["utils"]


def download_interrogator_assets(
    model_key: str,
    interrogator: "Interrogator",
    *,
    continue_to_tagging: bool = False,
) -> None:
    """
    Download missing files with WebUI progress updates.

    continue_to_tagging=False: prefetch finished → phase done + release busy.
    continue_to_tagging=True: keep busy, switch to tagging phase for follow-up job.
    """
    kwargs = _hf_kwargs(interrogator)
    files = _asset_filenames(interrogator)
    if not files:
        raise ValueError(f"模型 {model_key} 无可用下载文件列表")

    tagger_progress.begin_download(model_key, len(files), message="正在下载模型…")

    for index, filename in enumerate(files, start=1):
        tagger_progress.check_cancelled()
        tagger_progress.set_download(index, len(files), filename)
        with _hub_download_progress(index, len(files), filename):
            hf_hub_download(**kwargs, filename=filename)
        tagger_progress.set_download_bytes(
            file_index=index,
            file_total=len(files),
            filename=filename,
            bytes_current=0,
            bytes_total=0,
        )

    if continue_to_tagging:
        tagger_progress.complete_download_for_tagging(
            model_key,
            f"模型 {model_key} 已就绪，开始打标…",
        )
    else:
        tagger_progress.finish_download_success(f"模型 {model_key} 已就绪")


def ensure_interrogator_assets(model_key: str, interrogator: "Interrogator") -> bool:
    """
    Ensure model files exist locally before tagging.

    Returns True if a download was performed (caller should expect brief load after).
    """
    if interrogator_assets_ready(interrogator, model_key):
        return False
    download_interrogator_assets(model_key, interrogator, continue_to_tagging=True)
    return True


ALLOWED_DOWNLOAD_ENDPOINTS = {
    "",
    "https://hf-mirror.com",
    "https://modelscope.cn",
}


def normalize_download_endpoint(endpoint: str | None) -> str:
    value = (endpoint or "").strip().rstrip("/")
    if value not in ALLOWED_DOWNLOAD_ENDPOINTS:
        return ""
    return value


@contextmanager
def use_download_endpoint(endpoint: str | None) -> Iterator[None]:
    endpoint_value = normalize_download_endpoint(endpoint)
    previous = os.environ.get("HF_ENDPOINT")
    try:
        if endpoint_value:
            os.environ["HF_ENDPOINT"] = endpoint_value
        yield
    finally:
        if previous is None:
            os.environ.pop("HF_ENDPOINT", None)
        else:
            os.environ["HF_ENDPOINT"] = previous

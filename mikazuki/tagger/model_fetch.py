"""Download interrogator assets from Hugging Face with progress reporting."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator

from huggingface_hub import hf_hub_download, try_to_load_from_cache

from mikazuki.tagger.local_models import (
    asset_filenames,
    local_model_asset_paths,
    local_model_dir,
)
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


def describe_interrogator_asset_status(
    model_key: str,
    interrogator: "Interrogator",
) -> tuple[bool, str]:
    """Return (ready, multi-line console message)."""
    local_paths = local_model_asset_paths(model_key, interrogator)
    if local_paths:
        return True, (
            f"[tagger] 模型 {model_key} 已在本地"
        )

    kwargs = _hf_kwargs(interrogator)
    repo_id = kwargs.get("repo_id", model_key)
    files = _asset_filenames(interrogator)
    local_dir = local_model_dir(model_key)
    missing = [name for name in files if not _file_cached(kwargs, name)]
    if files and not missing:
        return True, (
            f"[tagger] 模型 {model_key} 已在 Hugging Face 本地缓存: {repo_id}"
        )
    file_hint = ", ".join(missing or files)
    return False, (
        f"[tagger] 模型 {model_key} 未在本地\n"
        "  请检查配置的 tagger-models 模型目录\n"
        f"  缺少文件: {file_hint}\n"
        f"  将尝试从 Hugging Face 下载: {repo_id}"
    )


def format_tagger_download_error(model_key: str, exc: BaseException) -> str:
    """User-facing hint: missing model vs network vs hub mis-route."""
    message = str(exc).strip()
    lowered = message.lower()
    exc_name = type(exc).__name__
    # Classify the original error locally, but never echo provider bodies,
    # credentials or absolute cache paths to the console or WebUI.
    message = exc_name

    if exc_name in {"LocalEntryNotFoundError", "OfflineModeIsEnabled"}:
        return (
            f"打标模型 {model_key} 未在本地，且无法从 Hugging Face 拉取文件。"
            " 请检查网络能否访问 huggingface.co，或将 model.onnx / selected_tags.csv "
            f"放入 tagger-models/wd14/{model_key}/ 后重试。"
            f"（{exc_name}: {message}）"
        )

    if exc_name in {"ConnectTimeout", "ReadTimeout", "TimeoutError"} or "timeout" in lowered:
        return (
            f"下载打标模型 {model_key} 超时，可能是网络不稳定或无法访问 Hugging Face。"
            f" 可稍后重试，或手动下载后放入 tagger-models/wd14/{model_key}/。"
            f"（{message}）"
        )

    if exc_name in {"ConnectionError", "ConnectError", "NetworkError"} or "connection" in lowered:
        return (
            f"无法连接 Hugging Face 下载打标模型 {model_key}。"
            " 请检查网络/代理；整合包默认模型已内置，其它模型需能访问 huggingface.co。"
            f"（{message}）"
        )

    if exc_name == "HTTPError" or "404" in lowered:
        if "modelscope" in lowered:
            return (
                f"魔搭 ModelScope 上不存在打标模型 {model_key}（SmilingWolf 系列仅托管在 Hugging Face）。"
                " 请勿强制 MIKAZUKI_HUB_BACKEND=modelscope；"
                f"或手动放入 tagger-models/wd14/{model_key}/。"
                f"（{message}）"
            )
        return (
            f"在 Hugging Face 未找到打标模型 {model_key} 的文件。"
            f" 请确认模型名称正确，或手动放入 tagger-models/wd14/{model_key}/。"
            f"（{message}）"
        )

    if "modelscope" in lowered and ("not exist" in lowered or "not exists" in lowered):
        return (
            f"魔搭 ModelScope 上不存在打标模型 {model_key}（SmilingWolf 系列仅托管在 Hugging Face）。"
            " 请勿强制 MIKAZUKI_HUB_BACKEND=modelscope；"
            f"或手动放入 tagger-models/wd14/{model_key}/。"
            f"（{message}）"
        )

    if "repository not found" in lowered or "repo not found" in lowered:
        return (
            f"Hugging Face 仓库不存在: {model_key}。"
            f"（{message}）"
        )

    return f"下载打标模型 {model_key} 失败: {message}"


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
    """Bridge Hugging Face hub tqdm bytes to tagger_progress API and console."""

    _file_index: int = 1
    _file_total: int = 1
    _filename: str = ""
    _last_print_pct: int = -1

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
        if total > 0:
            pct = min(100, int(current * 100 / total))
            if pct >= self._last_print_pct + 10 or (pct == 100 and self._last_print_pct < 100):
                self._last_print_pct = pct
                mb_done = current / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                print(
                    f"[tagger] 下载 {self._filename}: {pct}% "
                    f"({mb_done:.1f}/{mb_total:.1f} MB)",
                    flush=True,
                )
        return result


@contextmanager
def _hub_download_progress(file_index: int, file_total: int, filename: str) -> Iterator[None]:
    import huggingface_hub.utils as hf_utils

    class _BoundTaggerDownloadTqdm(_TaggerDownloadTqdm):
        _file_index = file_index
        _file_total = file_total
        _filename = filename
        _last_print_pct = -1

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
    ready, status_msg = describe_interrogator_asset_status(model_key, interrogator)
    print(status_msg, flush=True)
    if ready:
        msg = f"模型 {model_key} 已在本地"
        if continue_to_tagging:
            tagger_progress.complete_download_for_tagging(model_key, f"{msg}，开始打标…")
        else:
            tagger_progress.finish_download_success(msg)
        return

    kwargs = _hf_kwargs(interrogator)
    files = _asset_filenames(interrogator)
    if not files:
        raise ValueError(f"模型 {model_key} 无可用下载文件列表")

    tagger_progress.begin_download(model_key, len(files), message="正在下载模型…")
    repo_id = kwargs.get("repo_id", model_key)
    print(
        f"[tagger] 开始下载 {model_key}（共 {len(files)} 个文件，来源 {repo_id}）…",
        flush=True,
    )

    for index, filename in enumerate(files, start=1):
        tagger_progress.check_cancelled()
        tagger_progress.set_download(index, len(files), filename)
        print(
            f"[tagger] ({index}/{len(files)}) {filename} …",
            flush=True,
        )
        try:
            with _hub_download_progress(index, len(files), filename):
                path = hf_hub_download(**kwargs, filename=filename)
            print(f"[tagger] 已完成 {filename}", flush=True)
        except TaggerCancelled:
            raise
        except Exception as exc:
            hint = format_tagger_download_error(model_key, exc)
            print(f"[tagger] 失败: {hint}", flush=True)
            raise RuntimeError(hint) from exc
        tagger_progress.set_download_bytes(
            file_index=index,
            file_total=len(files),
            filename=filename,
            bytes_current=0,
            bytes_total=0,
        )

    print(f"[tagger] 模型 {model_key} 全部文件下载完成", flush=True)
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
        if endpoint_value in {"https://hf-mirror.com", "https://modelscope.cn"}:
            from mikazuki.china_hub import enable_china_hub

            enable_china_hub(force=endpoint_value == "https://modelscope.cn")
        yield
    finally:
        if previous is None:
            os.environ.pop("HF_ENDPOINT", None)
        else:
            os.environ["HF_ENDPOINT"] = previous

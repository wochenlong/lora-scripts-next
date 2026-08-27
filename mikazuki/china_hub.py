"""Domestic Hugging Face downloads via ModelScope's official hub patch.

hf-mirror.com only mirrors metadata; /resolve/ file URLs redirect (308) back to
huggingface.co. Setting HF_ENDPOINT=https://modelscope.cn does not work either
because huggingface_hub speaks a different API than ModelScope.

ModelScope ships ``modelscope.utils.hf_util.patch_hub()`` which replaces
``hf_hub_download`` / ``snapshot_download`` so transformers and sd-scripts keep
using Hugging Face repo ids in code while files are fetched from modelscope.cn.
Note: the patched downloader stores snapshots in ModelScope's own cache and
ignores the HF ``cache_dir`` argument — callers needing assets at a specific
location must resolve them from the ModelScope cache instead.

Some Hugging Face repo ids differ on ModelScope (e.g. openai/clip-vit-large-patch14
→ AI-ModelScope/clip-vit-large-patch14). ``HF_TO_MODELSCOPE_REPOS`` handles that.
"""

from __future__ import annotations

import os
from typing import Any, Callable

_PATCHED = False
_ORIGINAL_HF_HUB_DOWNLOAD: Callable[..., Any] | None = None

# WD/CL tagger ONNX repos are Hugging Face–only; ModelScope returns 404 for them.
_HF_ONLY_REPO_PREFIXES = ("SmilingWolf/", "cella110n/")

# Hugging Face repo id → ModelScope repo id.
#
# Only list ids that differ on ModelScope, plus same-id passthroughs for discoverability
# (remap_hf_repo_id returns the key when unlisted).
#
# Train-type coverage (vendor/sd-scripts/library/strategy_*.py):
#   SD1.5      — openai/clip-vit-large-patch14 (remapped)
#   SDXL/SD3   — clip-l (remapped), laion/CLIP-ViT-bigG-14-laion2B-39B-b160k (same id)
#   Flux/SD3   — clip-l (remapped), google/t5-v1_1-xxl (same id)
#   Lumina     — google/gemma-2-2b (same id)
#   Hunyuan    — google/byt5-small, Qwen/Qwen2.5-VL-7B-Instruct (same ids)
#   Anima      — no HF hub downloads at runtime (local_files_only + configs/t5_old, qwen3_06b)
HF_TO_MODELSCOPE_REPOS: dict[str, str] = {
    # SD1.5 / SDXL / Flux / SD3 — CLIP-L tokenizer
    "openai/clip-vit-large-patch14": "AI-ModelScope/clip-vit-large-patch14",
    # Flux / SD3 — T5-XXL tokenizer (verified same repo id on modelscope.cn)
    "google/t5-v1_1-xxl": "google/t5-v1_1-xxl",
    # SDXL / SD3 — CLIP-G tokenizer (same repo id on ModelScope)
    "laion/CLIP-ViT-bigG-14-laion2B-39B-b160k": "laion/CLIP-ViT-bigG-14-laion2B-39B-b160k",
}

# Back-compat alias used by tokenizer prefetch.
MODELSCOPE_TOKENIZER_REPOS = HF_TO_MODELSCOPE_REPOS


def remap_hf_repo_id(repo_id: str) -> str:
    return HF_TO_MODELSCOPE_REPOS.get(repo_id, repo_id)


def is_hf_only_repo(repo_id: str) -> bool:
    """Repos that must download from huggingface.co (not ModelScope)."""
    return str(repo_id or "").startswith(_HF_ONLY_REPO_PREFIXES)


def _hf_hub_download_direct(*args: Any, **kwargs: Any) -> Any:
    """Download via pre-patch huggingface_hub (bypass ModelScope patch)."""
    if _ORIGINAL_HF_HUB_DOWNLOAD is None:
        import huggingface_hub

        return huggingface_hub.hf_hub_download(*args, **kwargs)

    prev_endpoint = os.environ.get("HF_ENDPOINT")
    try:
        # hf-mirror only mirrors metadata; large ONNX files must come from hf.co.
        os.environ.pop("HF_ENDPOINT", None)
        if args:
            args = (remap_hf_repo_id(str(args[0])), *args[1:])
        if kwargs.get("repo_id") is not None:
            kwargs = {**kwargs, "repo_id": remap_hf_repo_id(str(kwargs["repo_id"]))}
        return _ORIGINAL_HF_HUB_DOWNLOAD(*args, **kwargs)
    finally:
        if prev_endpoint is None:
            os.environ.pop("HF_ENDPOINT", None)
        else:
            os.environ["HF_ENDPOINT"] = prev_endpoint


def hub_backend() -> str:
    """Return ``modelscope`` or ``huggingface`` for download routing."""
    explicit = (os.environ.get("MIKAZUKI_HUB_BACKEND") or "auto").strip().lower()
    if explicit in {"hf", "huggingface", "direct"}:
        return "huggingface"
    if explicit in {"ms", "modelscope", "魔搭"}:
        return "modelscope"

    endpoint = (os.environ.get("HF_ENDPOINT") or "").strip().lower()
    if "modelscope" in endpoint or "hf-mirror" in endpoint:
        return "modelscope"

    if explicit == "auto":
        try:
            from mikazuki.launch_utils import network_gfw_test

            if not network_gfw_test():
                return "modelscope"
        except Exception:
            return "modelscope"

    return "huggingface"


def _wrap_repo_remap(fn: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        repo_id = str(kwargs.get("repo_id") or (args[0] if args else ""))
        if is_hf_only_repo(repo_id):
            return _hf_hub_download_direct(*args, **kwargs)
        if args:
            args = (remap_hf_repo_id(str(args[0])), *args[1:])
        if kwargs.get("repo_id") is not None:
            kwargs = {**kwargs, "repo_id": remap_hf_repo_id(str(kwargs["repo_id"]))}
        return fn(*args, **kwargs)

    return wrapped


def _apply_repo_id_remapping() -> None:
    import huggingface_hub

    huggingface_hub.hf_hub_download = _wrap_repo_remap(huggingface_hub.hf_hub_download)  # type: ignore[method-assign]
    huggingface_hub.file_download.hf_hub_download = huggingface_hub.hf_hub_download  # type: ignore[attr-defined]
    if hasattr(huggingface_hub, "snapshot_download"):
        huggingface_hub.snapshot_download = _wrap_repo_remap(huggingface_hub.snapshot_download)  # type: ignore[method-assign]

    # patch_hub() may import transformers before we remap; re-bind its cached import.
    try:
        import transformers.utils.hub as transformers_hub

        transformers_hub.hf_hub_download = huggingface_hub.hf_hub_download
        if hasattr(huggingface_hub, "snapshot_download") and hasattr(transformers_hub, "snapshot_download"):
            transformers_hub.snapshot_download = huggingface_hub.snapshot_download
    except ImportError:
        pass


def _patch_modelscope_download_aliases() -> None:
    """Remap HF repo ids inside ModelScope download entrypoints."""
    import modelscope
    import modelscope.hub.file_download as ms_file

    if not getattr(ms_file, "_mikazuki_repo_remap_patched", False):
        original_file = ms_file.model_file_download

        def model_file_download(model_id: str, *args: Any, **kwargs: Any) -> str:
            return original_file(remap_hf_repo_id(model_id), *args, **kwargs)

        ms_file.model_file_download = model_file_download  # type: ignore[assignment]
        ms_file._mikazuki_repo_remap_patched = True  # type: ignore[attr-defined]

    if not getattr(modelscope, "_mikazuki_repo_remap_patched", False):
        original_snapshot = modelscope.snapshot_download

        def snapshot_download(model_id: str, *args: Any, **kwargs: Any) -> str:
            return original_snapshot(remap_hf_repo_id(model_id), *args, **kwargs)

        modelscope.snapshot_download = snapshot_download  # type: ignore[assignment]
        modelscope._mikazuki_repo_remap_patched = True  # type: ignore[attr-defined]


def enable_china_hub(*, force: bool = False) -> bool:
    """Route huggingface_hub downloads through ModelScope when appropriate.

    Safe to call multiple times. Returns True when ModelScope patch is active.
    """
    global _PATCHED, _ORIGINAL_HF_HUB_DOWNLOAD
    if _PATCHED:
        return True
    if not force and hub_backend() != "modelscope":
        return False

    try:
        from modelscope.utils.hf_util import patch_hub
    except ImportError:
        return False

    try:
        import huggingface_hub

        if _ORIGINAL_HF_HUB_DOWNLOAD is None:
            _ORIGINAL_HF_HUB_DOWNLOAD = huggingface_hub.hf_hub_download
    except ImportError:
        pass

    try:
        import diffusers  # noqa: F401
        import peft  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        pass

    _patch_modelscope_download_aliases()
    patch_hub()
    _apply_repo_id_remapping()
    _PATCHED = True
    return True


def china_hub_status() -> dict[str, str | bool]:
    return {
        "backend": hub_backend(),
        "patched": _PATCHED,
        "hf_endpoint": os.environ.get("HF_ENDPOINT") or "",
    }

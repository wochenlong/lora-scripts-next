"""Read-only model capabilities for Dataset Tagger; never downloads assets."""
from __future__ import annotations

from .local_models import local_model_asset_paths

TAG_MODEL_IDS = (
    "wd14-convnextv2-v2", "wd-convnext-v3", "wd-swinv2-v3", "wd-vit-v3",
    "wd14-swinv2-v2", "wd14-vit-v2", "wd14-moat-v2",
    "wd-eva02-large-tagger-v3", "wd-vit-large-tagger-v3", "cl_tagger_1_01",
)
TAG_PARAMETERS = (
    "threshold", "character_threshold", "add_rating_tag", "add_model_tag",
    "additional_tags", "exclude_tags", "escape_tag", "replace_underscore",
    "replace_underscore_excludes", "download_endpoint", "interrogator_model",
)
CAPTION_PARAMETERS = ("prompt", "system_prompt", "prompt_id", "language", "max_caption_length", "max_tokens", "temperature", "allow_local_fallback", "use_cache", "profile_id")


def model_catalog(config: dict, local_status: dict) -> list[dict]:
    from .interrogator import available_interrogators
    models = []
    for model_id in TAG_MODEL_IDS:
        interrogator = available_interrogators[model_id]
        downloaded = any(local_model_asset_paths(identifier, interrogator) for identifier in (model_id, *getattr(interrogator, "local_model_aliases", ())))
        # Local Hub-cache queries only. Do not trigger a download from this endpoint.
        if not downloaded:
            from huggingface_hub import try_to_load_from_cache
            from .local_models import asset_filenames
            filenames = asset_filenames(interrogator)
            options = getattr(interrogator, "kwargs", {})
            repo = options.get("repo_id")
            if repo and filenames:
                downloaded = all(isinstance(try_to_load_from_cache(repo, name, revision=options.get("revision")), str) for name in filenames)
        models.append({
            "id": model_id, "name": model_id, "model": model_id,
            "family": "CL" if model_id.startswith("cl_") else "WD",
            "author": "cella110n" if model_id.startswith("cl_") else "SmilingWolf",
            "runtime": "local", "output": "tag", "capabilities": ["tag"],
            "languages": ["native"], "downloaded": downloaded, "ready": True,
            "profile_id": None, "parameters": list(TAG_PARAMETERS),
        })
    for profile in config.get("profiles", []):
        if not profile.get("enabled", True) or "vision" not in profile.get("capabilities", []):
            continue
        model_name = str(profile.get("model") or "")
        remote = profile.get("source") == "remote"
        models.append({
            "id": "llm:" + profile["id"], "name": profile.get("name") or model_name, "model": model_name,
            "family": "Qwen-VL" if "qwen" in model_name.lower() else "Vision LLM",
            "author": model_name.split("/")[0] if "/" in model_name else "",
            "runtime": "api" if remote else "local", "output": "natural",
            "capabilities": ["caption", "vision"], "languages": profile.get("languages", []),
            "downloaded": bool(local_status.get("installed")) if profile.get("source") == "managed-local" else False,
            "ready": bool(profile.get("ready", False)), "profile_id": profile["id"],
            "parameters": list(CAPTION_PARAMETERS),
        })
    local_id = "qwen3-vl-2b-local"
    if not any(item.get("profile_id") == local_id for item in models):
        models.append({
            "id": "llm:" + local_id, "name": "Qwen3-VL-2B", "model": "Qwen3VL-2B-Instruct-Q4_K_M.gguf",
            "family": "Qwen-VL", "author": "Qwen", "runtime": "local", "output": "natural",
            "capabilities": ["caption", "vision"], "languages": ["zh-CN", "en"],
            "downloaded": bool(local_status.get("installed")), "ready": False,
            "profile_id": local_id, "parameters": list(CAPTION_PARAMETERS),
        })
    return models


def validate_model_selection(payload: dict, config: dict) -> None:
    from mikazuki.llm.contracts import LLMContractError
    model_id = payload.get("model_id")
    runtime = payload.get("runtime")
    if not model_id:
        if runtime:
            raise LLMContractError("runtime requires model_id")
        return  # Existing Tag/Caption APIs remain usable without catalog fields.
    if payload.get("mode") == "tag":
        if model_id not in TAG_MODEL_IDS or runtime != "local" or payload.get("interrogator_model") != model_id:
            raise LLMContractError("selected Tag model does not match runtime or parameters")
        return
    selected = next((profile for profile in config.get("profiles", []) if "llm:" + profile["id"] == model_id), None)
    if selected is None or not selected.get("enabled", True) or "vision" not in selected.get("capabilities", []):
        raise LLMContractError("selected Caption model must have vision capability")
    expected = "api" if selected.get("source") == "remote" else "local"
    if runtime != expected or payload.get("profile_id") != selected["id"]:
        raise LLMContractError("selected model does not match runtime or profile")

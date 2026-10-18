"""Pinned, deliberately MOSS-only engine registration."""

ENGINE_ID = "moss"
KIND = "plugin"
TRAIN_TYPES = {"moss-image-anima-lora": "moss-image"}
UPSTREAM = {
    "repo": "sorryhyun/anima_lora",
    "branch": "moss_lora",
    "commit": "1df6181fcea45926932fb63d5924f6f3dfd7c7d0",
    "github": "https://github.com/sorryhyun/anima_lora.git",
    "zip": None,
    "gitee": None,
}
FEATURE_FLAG_ENV = "LORA_ENABLE_MOSS"
CAPABILITIES = {"model_families": ["moss-image"], "tasks": ["lora"], "variants": ["moss-image"]}
PATCHES = []
REQUIRES = {"python": "3.13", "accelerator": "cuda"}
SLIM_SUPPORTED = False

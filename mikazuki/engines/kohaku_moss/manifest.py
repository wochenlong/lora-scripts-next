"""Pinned KohakuMossTrainer engine registration."""

ENGINE_ID = "kohaku-moss"
KIND = "plugin"
TRAIN_TYPES = {"kohaku-moss-image-lora": "moss-image"}
UPSTREAM = {
    "repo": "KohakuBlueleaf/KohakuMossTrainer",
    "branch": "main",
    "commit": "5bb1a81ed030cc87c540d5e02fe60aab887199b4",
    "github": "https://github.com/KohakuBlueleaf/KohakuMossTrainer.git",
    "zip": None,
    "gitee": None,
}
FEATURE_FLAG_ENV = "LORA_ENABLE_KOHAKU_MOSS"
CAPABILITIES = {
    "model_families": ["moss-image"],
    "tasks": ["lora"],
    "variants": ["moss-image"],
}
PATCHES = ["windows-triton-called-process-fallback-v1"]
REQUIRES = {"python": "3.12", "accelerator": "cuda"}
SLIM_SUPPORTED = False

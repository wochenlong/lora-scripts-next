"""AI Toolkit (ostris/ai-toolkit) engine pack manifest (contract: mikazuki.engines.manifest)."""

ENGINE_ID = "ai-toolkit"
KIND = "plugin"

TRAIN_TYPES = {
    "klein-4b-lora": "klein-4b",
    "klein-9b-lora": "klein-9b",
}

UPSTREAM = {
    "repo": "ostris/ai-toolkit",
    # Pinned at research snapshot (2026-08-28). config/ai_toolkit_backend.toml
    # or the install API payload may override.
    "commit": "5497a001cb8752c665f93907a0393fc612116fd5",
    "zip": None,
    "github": "https://github.com/ostris/ai-toolkit.git",
    "gitee": None,
}

FEATURE_FLAG_ENV = "LORA_ENABLE_AI_TOOLKIT"

CAPABILITIES = {
    "model_families": ["flux2-klein"],
    "tasks": ["lora"],
    "variants": ["klein-4b", "klein-9b"],
}

PATCHES = []

REQUIRES = {}
SLIM_SUPPORTED = False

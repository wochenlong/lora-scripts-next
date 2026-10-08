"""AI Toolkit (ostris/ai-toolkit) engine pack manifest (contract: mikazuki.engines.manifest)."""

ENGINE_ID = "ai-toolkit"
KIND = "plugin"

from .capabilities import MODELS, TRAIN_TYPES

UPSTREAM = {
    "repo": "ostris/ai-toolkit",
    # Includes Qwen Image 2.1 and the local-first component loaders.
    "commit": "ecee894ed2b1f3716d9d7326693061ec1a3105bb",
    "zip": None,
    "github": "https://github.com/ostris/ai-toolkit.git",
    "gitee": None,
}

FEATURE_FLAG_ENV = "LORA_ENABLE_AI_TOOLKIT"

CAPABILITIES = {
    "model_families": ["sdxl", "flux", "flux2-klein", "krea2", "anima", "qwen-image-21"],
    "tasks": ["lora"],
    "variants": list(MODELS),
    "models": MODELS,
}

PATCHES = []

REQUIRES = {}
SLIM_SUPPORTED = False

"""kohya builtin engine pack manifest (contract: mikazuki.engines.manifest).

kohya ships inside the main Python environment and is always ready: no
installer, no patches, dispatch goes straight to the existing trainer_mapping
pipeline. (No lumina entry exists in trainer_mapping today; capabilities
mirror the real mapping.)
"""

ENGINE_ID = "kohya"
KIND = "builtin"

TRAIN_TYPES = {
    "sd-lora": "sd15",
    "sdxl-lora": "sdxl",
    "sd-dreambooth": "sd15",
    "sdxl-finetune": "sdxl",
    "sd3-lora": "anima",
    "anima-lora": "anima",
    "anima-finetune": "anima",
    "flux-lora": "flux",
    "flux-finetune": "flux",
}

UPSTREAM = {
    "repo": "kohya-ss/sd-scripts",
    # Built in to the distribution; version is whatever the package ships.
    "commit": "",
    "zip": None,
    "github": "https://github.com/kohya-ss/sd-scripts.git",
    "gitee": None,
}

FEATURE_FLAG_ENV = ""

CAPABILITIES = {
    "model_families": ["sd15", "sdxl", "anima", "flux"],
    "tasks": ["lora", "finetune", "dreambooth"],
    "variants": ["sd15", "sdxl", "anima", "flux"],
}

PATCHES = []

REQUIRES = {}
SLIM_SUPPORTED = False

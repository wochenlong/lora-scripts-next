"""musubi-tuner engine pack manifest (contract: mikazuki.engines.manifest)."""

ENGINE_ID = "musubi"
KIND = "plugin"

TRAIN_TYPES = {
    "krea2-lora": "krea2",
}

UPSTREAM = {
    "repo": "kohya-ss/musubi-tuner",
    # No repo-wide default pin: the commit comes from config/musubi_backend.toml
    # or the install API payload at install time.
    "commit": "",
    "zip": None,
    "github": "https://github.com/kohya-ss/musubi-tuner.git",
    "gitee": None,
}

FEATURE_FLAG_ENV = "LORA_ENABLE_MUSUBI"

CAPABILITIES = {
    "model_families": ["krea2"],
    "tasks": ["lora"],
    "variants": ["krea2"],
}

PATCHES = []

REQUIRES = {}
SLIM_SUPPORTED = False

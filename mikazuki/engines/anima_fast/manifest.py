"""Anima Fast engine pack manifest (contract: mikazuki.engines.manifest)."""

ENGINE_ID = "anima-fast"
KIND = "plugin"

TRAIN_TYPES = {
    "anima-lora-fast": "anima",
}

UPSTREAM = {
    "repo": "sorryhyun/anima_lora",
    # Shipped default pin; config/anima_fast_backend.toml source_commit overrides.
    "commit": "b43928b5e4b82b907bfca1a322383a33088d0bdd",
    "zip": None,
    "github": "https://github.com/sorryhyun/anima_lora.git",
    "gitee": None,
}

FEATURE_FLAG_ENV = "LORA_ENABLE_ANIMA_FAST"

CAPABILITIES = {
    "model_families": ["anima"],
    "tasks": ["lora"],
    "variants": ["anima"],
}

PATCHES = []

REQUIRES = {}
SLIM_SUPPORTED = False

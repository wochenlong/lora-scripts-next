"""musubi-tuner engine pack manifest (contract: mikazuki.engines.manifest)."""

ENGINE_ID = "musubi"
KIND = "plugin"

TRAIN_TYPES = {
    "krea2-lora": "krea2",
}

UPSTREAM = {
    "repo": "kohya-ss/musubi-tuner",
    # Default pin (2026-08-13, verified on GB10). config/musubi_backend.toml
    # or the install API payload may override.
    "commit": "e0cbd8f3dfe38365b10f8bc790b980f8894e8ba1",
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

# Cloud slim install (start_cloud.sh): musubi-tuner keeps torch out of its
# base dependencies (torch only enters via the cu12x extras), so installing
# the package without extras never touches the host torch. Ranges mirror the
# upstream extras floor (cu124 -> torch>=2.5.1) and requires-python.
REQUIRES = {
    "python": ">=3.10,<3.13",
    "torch": ">=2.5.1",
    "cuda": ">=12.4",
}
SLIM_SUPPORTED = True

ENGINE_ID = "diffsynth"
KIND = "plugin"
TRAIN_TYPES = {"qwen-image-21-lora": "qwen-image-21"}
UPSTREAM = {
    "repo": "modelscope/DiffSynth-Studio",
    "commit": "7686e54d41d25c0e8ed5f1318acc23b6bb832654",
    "github": "https://github.com/modelscope/DiffSynth-Studio.git",
    "zip": None,
    "gitee": None,
}
FEATURE_FLAG_ENV = "LORA_ENABLE_DIFFSYNTH"
CAPABILITIES = {"model_families": ["qwen-image-21"], "tasks": ["lora"], "variants": ["qwen-image-21"]}
PATCHES = []
REQUIRES = {}
SLIM_SUPPORTED = False

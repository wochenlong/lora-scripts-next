"""Engine pack manifest — contract: mikazuki/engines/manifest.py.

职责：pack 名片。registry 扫描时只读这个文件；字段不全会在扫描时响亮报错。
完成判据：`python -c "from mikazuki.engines import registry; registry.discover_packs()"`
能看到你的 ENGINE_ID，且 train_type_map() 包含你的 TRAIN_TYPES。
"""

# 唯一引擎 id，同时是路由段 /api/engines/<id>/。
ENGINE_ID = "your-engine"

# "plugin"（可安装，独立 venv）或 "builtin"（随主环境，恒 ready）。
KIND = "plugin"

# UI train_type -> variant。/api/run 的分发键；一个引擎可挂多个 train_type。
TRAIN_TYPES = {
    "your-train-type": "default-variant",
}

# 上游钉版。下载优先级：zip（整体分发包）→ github → gitee fallback。
# 无论走哪个渠道，repo + commit 都必须能钉住版本。
UPSTREAM = {
    "repo": "owner/repo",
    "commit": "<pinned sha；空串 = 由 config/<id>_backend.toml 或安装 API 决定>",
    "zip": None,
    "github": "https://github.com/owner/repo.git",
    "gitee": None,
}

# 维护者紧急关闭开关：该环境变量 =0 时引擎隐藏。builtin 可留空。
FEATURE_FLAG_ENV = "LORA_ENABLE_YOUR_ENGINE"

# 能力矩阵（模型族 × 任务 × 变体），自由格式，前端与文档据此展示。
CAPABILITIES = {
    "model_families": [],
    "tasks": ["lora"],
    "variants": [],
}

# 安装期补丁清单（patches/ 下的 unified diff，头部格式见 patches/README.md）。
PATCHES = []

# 占位：云精简安装的宿主要求 / 是否支持 slim。目前只有 isolated 安装。
REQUIRES = {}
SLIM_SUPPORTED = False

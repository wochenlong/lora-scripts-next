"""settings.py stub — 运行时发现与配置文件。

职责：定义 RuntimeConfig（源码根、venv python、输出/日志/缓存目录），
从 config/<id>_backend.toml + 环境变量 + 默认布局发现运行时；
提供 feature_enabled()（读 manifest.FEATURE_FLAG_ENV 的 kill switch）。
输入：项目根 Path；输出：RuntimeConfig dataclass。
完成判据：默认布局下 discover_runtime() 不抛异常，kill switch 生效。
参考：mikazuki/engines/musubi/settings.py。
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    source_root: Path
    python: Path
    lora_next_root: Path
    output_dir: Path
    logging_dir: Path
    cache_dir: Path


def feature_enabled() -> bool:
    return True


def discover_runtime(lora_next_root: Path | None = None) -> RuntimeConfig:
    root = (lora_next_root or Path.cwd()).resolve()
    raise NotImplementedError("fill in discovery: config file -> env vars -> default layout")

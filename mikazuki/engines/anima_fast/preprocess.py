from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from .adapter import AdapterError, AdaptedConfig, adapt_config, is_empty
from .settings import RuntimeConfig


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".avif"}
OUTPUT_DIR_KEYS = ("output_dir", "logging_dir", "lora_cache_dir", "resized_image_dir")


@dataclass(frozen=True)
class DatasetPrepareResult:
    adapted: AdaptedConfig
    warnings: list[str]
    auto_resized: bool = False


def user_left_resized_empty(source: dict) -> bool:
    return is_empty(source.get("resized_image_dir"))


def _parse_resolution(value: object) -> int:
    text = str(value or "1024,1024").replace("x", ",")
    nums: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if part.isdigit():
            nums.append(int(part))
    return max(nums) if nums else 1024


def _has_images(root: Path | None) -> bool:
    if root is None or not root.is_dir():
        return False
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            return True
    return False


def _image_keys(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {
        str(path.relative_to(root).with_suffix(""))
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS
    }


def ensure_output_directories(values: dict) -> list[str]:
    created: list[str] = []
    for key in OUTPUT_DIR_KEYS:
        raw = values.get(key)
        if not raw:
            continue
        path = Path(str(raw))
        if path.is_dir():
            continue
        path.mkdir(parents=True, exist_ok=True)
        created.append(str(path))
    return created


def run_resize_images(runtime: RuntimeConfig, src: Path, dst: Path, resolution: int) -> None:
    script = runtime.anima_root / "scripts" / "preprocess" / "resize_images.py"
    if not script.is_file():
        raise AdapterError(f"Anima resize script missing: {script}")
    if not src.is_dir():
        raise AdapterError(f"训练图片目录不存在: {src}")
    dst.mkdir(parents=True, exist_ok=True)
    command = [
        str(runtime.python),
        str(script),
        "--src",
        str(src.resolve()),
        "--dst",
        str(dst.resolve()),
        "--target_res",
        str(resolution),
        "--recursive",
        "--min_pixels",
        "0",
    ]
    completed = subprocess.run(
        command,
        cwd=str(runtime.anima_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise AdapterError(f"Anima resize 预处理失败: {detail or completed.returncode}")


def prepare_anima_fast_dataset(source: dict, runtime: RuntimeConfig, run_id: str) -> DatasetPrepareResult:
    adapted = adapt_config(source, runtime, run_id)
    values = dict(adapted.values)
    warnings = list(adapted.warnings)

    created = ensure_output_directories(values)
    for path in created:
        warnings.append(f"created missing directory: {path}")

    auto_resize = user_left_resized_empty(source)
    resized_dir = Path(str(values["resized_image_dir"]))
    source_dir_raw = values.get("source_image_dir")
    if not source_dir_raw:
        if auto_resize:
            raise AdapterError("自动 resize 需要填写训练图片目录 train_data_dir")
        return DatasetPrepareResult(adapted=AdaptedConfig(values=values, warnings=warnings))

    source_dir = Path(str(source_dir_raw))
    if auto_resize:
        if not _has_images(source_dir):
            raise AdapterError(f"训练图片目录中没有可用图片: {source_dir}")
        resized_keys = _image_keys(resized_dir)
        source_keys = _image_keys(source_dir)
        missing = source_keys - resized_keys
        extra = resized_keys - source_keys
        if not resized_keys or missing:
            resolution = _parse_resolution(source.get("resolution") or values.get("resolution"))
            run_resize_images(runtime, source_dir, resized_dir, resolution)
            remaining = missing - _image_keys(resized_dir)
            if remaining:
                examples = ", ".join(sorted(remaining)[:3])
                raise AdapterError(
                    f"resize 后仍缺少 {len(remaining)} 个训练图片缓存"
                    f"（示例: {examples}）"
                )
            if not resized_keys:
                warnings.append(
                    f"auto-resized images from {source_dir} to {resized_dir} at resolution {resolution}"
                )
            else:
                warnings.append(
                    f"源目录新增 {len(missing)} 张图片（resized 为历史任务快照），已增量补充 preprocess: {resized_dir}"
                )
            if extra:
                warnings.append(
                    f"resized 缓存中 {len(extra)} 张图片已不在源目录，仍会参与训练；如已弃用请清理 {resized_dir}"
                )
            return DatasetPrepareResult(
                adapted=AdaptedConfig(values=values, warnings=warnings),
                warnings=warnings,
                auto_resized=True,
            )
        if extra:
            warnings.append(
                f"resized 缓存中 {len(extra)} 张图片已不在源目录，仍会参与训练；如已弃用请清理 {resized_dir}"
            )
        warnings.append(f"using existing resized dataset at {resized_dir}")

    return DatasetPrepareResult(adapted=AdaptedConfig(values=values, warnings=warnings), warnings=warnings)

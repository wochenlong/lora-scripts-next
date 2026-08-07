from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import json
import os
import subprocess

from .settings import RuntimeConfig


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".avif"}


@dataclass
class ProbeFacts:
    python_version: str = ""
    torch_version: str = ""
    cuda_available: bool = False
    cuda_version: str = ""
    gpu_name: str = ""
    vram_total_mb: int = 0
    transformers_version: str = ""
    probe_error: str = ""


@dataclass
class PreflightResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "facts": self.facts,
        }


DependencyProbe = Callable[[RuntimeConfig], ProbeFacts]


def default_dependency_probe(runtime: RuntimeConfig) -> ProbeFacts:
    script = r"""
import json, platform
facts = {"python_version": platform.python_version()}
try:
    import torch
    facts["torch_version"] = getattr(torch, "__version__", "")
    facts["cuda_available"] = bool(torch.cuda.is_available())
    facts["cuda_version"] = getattr(torch.version, "cuda", "") or ""
    if torch.cuda.is_available():
        facts["gpu_name"] = torch.cuda.get_device_name(0)
        facts["vram_total_mb"] = int(torch.cuda.get_device_properties(0).total_memory // (1024 * 1024))
except Exception as exc:
    facts["torch_error"] = str(exc)
try:
    import transformers
    facts["transformers_version"] = getattr(transformers, "__version__", "")
except Exception:
    facts["transformers_version"] = ""
print(json.dumps(facts))
"""
    from .environment import probe_env

    completed = subprocess.run(
        [str(runtime.python), "-c", script],
        cwd=str(runtime.musubi_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env=probe_env(runtime),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "probe exited non-zero").strip()
        return ProbeFacts(probe_error=detail[:800])
    try:
        raw = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        stderr = (completed.stderr or completed.stdout or "invalid probe json").strip()
        return ProbeFacts(probe_error=stderr[:800])
    return ProbeFacts(
        python_version=str(raw.get("python_version", "")),
        torch_version=str(raw.get("torch_version", "")),
        cuda_available=bool(raw.get("cuda_available", False)),
        cuda_version=str(raw.get("cuda_version", "")),
        gpu_name=str(raw.get("gpu_name", "")),
        vram_total_mb=int(raw.get("vram_total_mb", 0) or 0),
        transformers_version=str(raw.get("transformers_version", "")),
    )


def _resolve(value: Any, base: Path) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _dataset_images(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]


def run_preflight(
    values: dict[str, Any],
    runtime: RuntimeConfig,
    dataset: dict[str, Any] | None = None,
    probe: DependencyProbe = default_dependency_probe,
) -> PreflightResult:
    """Validate adapted musubi config values (post-adapter, absolute paths)."""
    errors: list[str] = []
    warnings: list[str] = []
    facts: dict[str, Any] = {
        "musubi_root": str(runtime.musubi_root),
        "python": str(runtime.python),
    }

    if not runtime.python.is_file():
        errors.append(f"musubi-tuner venv python 不存在: {runtime.python}")

    for field_name in ("dit", "vae", "text_encoder"):
        raw = values.get(field_name)
        if raw is None or str(raw).strip() == "":
            errors.append(f"缺少必需模型字段: {field_name}")
        elif not Path(str(raw)).is_file():
            errors.append(f"模型文件不存在: {field_name}={raw}")
    turbo = values.get("turbo_dit")
    if turbo is not None and str(turbo).strip() and not Path(str(turbo)).is_file():
        errors.append(f"Turbo DiT 文件不存在: turbo_dit={turbo}")

    images: list[Path] = []
    for entry in (dataset or {}).get("datasets", []):
        image_dir = Path(str(entry.get("image_directory", "")))
        found = _dataset_images(image_dir)
        images.extend(found)
        if not found:
            errors.append(f"数据集目录没有图片: {image_dir}")
    facts["dataset_image_count"] = len(images)
    if images:
        caption_ext = str((dataset or {}).get("general", {}).get("caption_extension", ".txt"))
        captioned = sum(1 for image in images if image.with_suffix(caption_ext).is_file())
        if captioned < len(images):
            warnings.append(f"{len(images) - captioned} 张图片缺少 {caption_ext} caption 文件")

    if values.get("sample_prompts") and not values.get("text_encoder"):
        errors.append("启用采样预览（sample_prompts）需要 text_encoder（Qwen3-VL）路径")

    if not errors:
        dep = probe(runtime)
        facts.update(dep.__dict__)
        if dep.probe_error:
            errors.append(f"musubi-tuner 运行时探测失败（{runtime.python}）: {dep.probe_error}")
        elif not dep.cuda_available:
            errors.append("musubi-tuner 环境的 torch 未检测到 CUDA")
        if dep.transformers_version:
            try:
                major, minor = (int(part) for part in dep.transformers_version.split(".")[:2])
                if (major, minor) < (4, 57):
                    errors.append(
                        f"Krea 2 的 Qwen3-VL 文本编码器需要 transformers>=4.57，当前为 {dep.transformers_version}"
                    )
            except (ValueError, TypeError):
                warnings.append(f"无法解析 transformers 版本: {dep.transformers_version}")
        if dep.vram_total_mb and dep.vram_total_mb < 12000:
            warnings.append(f"显存 {dep.vram_total_mb} MB 可能不足以训练 Krea 2，建议开启 fp8_base + blocks_to_swap")

    return PreflightResult(ok=not errors, errors=errors, warnings=warnings, facts=facts)

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import json
import subprocess

from .adapter import VARIANTS
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
    completed = subprocess.run(
        [str(runtime.python), "-c", script],
        cwd=str(runtime.toolkit_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
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


def _dataset_images(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]


def run_preflight(
    config: dict[str, Any],
    runtime: RuntimeConfig,
    variant: str,
    probe: DependencyProbe = default_dependency_probe,
) -> PreflightResult:
    """Validate an adapted ai-toolkit config tree (post-adapter, absolute paths)."""
    errors: list[str] = []
    warnings: list[str] = []
    spec = VARIANTS.get(variant, {})
    facts: dict[str, Any] = {
        "toolkit_root": str(runtime.toolkit_root),
        "python": str(runtime.python),
        "variant": variant,
        "arch": spec.get("arch", ""),
    }

    if not runtime.python.is_file():
        errors.append(f"ai-toolkit venv python 不存在: {runtime.python}")

    process = (config.get("config", {}).get("process") or [{}])[0]
    model = process.get("model", {})
    datasets = process.get("datasets", [])

    name_or_path = str(model.get("name_or_path") or "").strip()
    if not name_or_path:
        errors.append("缺少 model.name_or_path（Klein DiT）")
    else:
        candidate = Path(name_or_path)
        if candidate.is_dir():
            dit_file = candidate / spec.get("dit_filename", "")
            if not dit_file.is_file():
                errors.append(f"DiT 文件不存在: {dit_file}（变体 {variant} 期望 {spec.get('dit_filename')}）")
            # VAE is a required local asset: runtime auto-download via hf-xet
            # proved unreliable (CAS 401); toolkit consumes <name_or_path>/ae.safetensors.
            if not (candidate / "ae.safetensors").is_file():
                errors.append(
                    f"VAE 未就位: {candidate / 'ae.safetensors'}。"
                    "请在「训练用模型」区下载 VAE（须与 DiT 同目录）"
                )
        elif not candidate.is_file():
            # HF repo id: downloaded upstream at runtime
            facts["dit_source"] = "huggingface"
            warnings.append(f"DiT 将按 HF repo 下载: {name_or_path}（需网络/HF 镜像可达）")
    facts["text_encoder"] = spec.get("text_encoder", "")
    facts["vae"] = "ae.safetensors（与 DiT 同目录）"
    warnings.append(
        f"TE ({spec.get('text_encoder', '')}) 默认从 HF 拉取；"
        "本地覆盖路径上游暂无 config 键（见 FIELD_NOTES）"
    )

    images: list[Path] = []
    for entry in datasets:
        folder = Path(str(entry.get("folder_path", "")))
        found = _dataset_images(folder)
        images.extend(found)
        if not found:
            errors.append(f"数据集目录没有图片: {folder}")
        for control_dir in entry.get("control_path") or []:
            if not Path(str(control_dir)).is_dir():
                errors.append(f"参考图目录不存在: {control_dir}")
    facts["dataset_image_count"] = len(images)
    if images and datasets:
        caption_ext = "." + str(datasets[0].get("caption_ext", "txt")).lstrip(".")
        captioned = sum(1 for image in images if image.with_suffix(caption_ext).is_file())
        if captioned < len(images):
            warnings.append(f"{len(images) - captioned} 张图片缺少 {caption_ext} caption 文件")

    if not errors:
        dep = probe(runtime)
        facts.update(dep.__dict__)
        if dep.probe_error:
            errors.append(f"ai-toolkit 运行时探测失败（{runtime.python}）: {dep.probe_error}")
        elif not dep.cuda_available:
            errors.append("ai-toolkit 环境的 torch 未检测到 CUDA")

    return PreflightResult(ok=not errors, errors=errors, warnings=warnings, facts=facts)

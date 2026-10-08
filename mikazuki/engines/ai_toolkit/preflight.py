from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import json
import subprocess

from .adapter import VARIANTS
from .settings import RuntimeConfig
from .environment import probe_env


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
        env=probe_env(runtime),
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


def run_preflight(
    config: dict[str, Any],
    runtime: RuntimeConfig,
    variant: str,
    te_path: str = "",
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
    datasets = process.get("datasets", [])

    assets = config.get("meta", {}).get("next_trainer", {}).get("assets")
    if not assets:
        errors.append("缺少模型输入模式与本地资产声明，请重新生成配置")
    else:
        from .model_inputs import validate_assets
        try:
            validate_assets(assets)
            facts["model_assets"] = assets
        except (ValueError, OSError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    if not (runtime.toolkit_root / "run.py").is_file():
        errors.append(f"AI Toolkit 启动脚本不存在: {runtime.toolkit_root / 'run.py'}")
    if variant == "qwen-image-21" and not (runtime.toolkit_root / "extensions_built_in/diffusion_models/qwen_image_2/qwen_image_2.py").is_file():
        errors.append("当前 AI Toolkit 版本不含 Qwen Image 2.1，请在设置中卸载后安装当前固定版本")
    facts["dataset_image_count"] = len({str(image.resolve()) for entry in datasets for image in Path(entry["folder_path"]).iterdir() if image.is_file() and image.suffix.lower() in IMAGE_EXTS})
    if not facts["dataset_image_count"]:
        errors.append("数据集目录没有图片")
    if not errors:
        try:
            dep = probe(runtime)
            facts.update(dep.__dict__)
            if dep.probe_error:
                errors.append(f"AI Toolkit 运行时探测失败: {dep.probe_error}")
            elif not dep.cuda_available:
                errors.append("AI Toolkit 环境的 torch 未检测到 CUDA")
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"AI Toolkit 运行时探测失败: {exc}")
    return PreflightResult(ok=not errors, errors=errors, warnings=warnings, facts=facts)

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import json
import re
import subprocess

from .adapter import VARIANTS
from .settings import RuntimeConfig


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".avif"}
HF_REPO_ID_RE = re.compile(r"^[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*$")


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
            # Without an explicit model.vae_path, keep the legacy colocated
            # VAE convention for old configs.
            colocated_vae = candidate / "ae.safetensors"
            if not model.get("vae_path") and not colocated_vae.is_file():
                errors.append(
                    f"VAE 未就位: {colocated_vae}。"
                    "请在「训练用模型」区填写或下载 VAE"
                )
        elif not candidate.is_file():
            # Anything that is neither an existing path nor a syntactically
            # valid HF repo id is a typo'd local path; error instead of
            # silently falling through to a runtime download (P8).
            if not HF_REPO_ID_RE.match(name_or_path):
                errors.append(
                    f"DiT 路径不存在且不是合法的 HF repo id: {name_or_path}。"
                    "请在「训练用模型」区下载，或检查路径是否写错"
                )
            else:
                facts["dit_source"] = "huggingface"
                warnings.append(f"DiT 将按 HF repo 下载: {name_or_path}（需网络/HF 镜像可达）")
    facts["text_encoder"] = te_path or spec.get("text_encoder", "")
    vae_path = str(model.get("vae_path") or "").strip()
    if vae_path:
        vae_file = Path(vae_path)
        facts["vae"] = vae_path
        if not vae_file.is_file():
            errors.append(f"VAE 文件不存在: {vae_file}")
    else:
        facts["vae"] = "ae.safetensors（旧配置：与 DiT 同目录）"
    if not te_path:
        errors.append("缺少本地文本编码器目录（text_encoder），请在「训练用模型」区下载")
    else:
        te_dir = Path(te_path)
        for name in ("config.json", "tokenizer.json", "tokenizer_config.json"):
            if not (te_dir / name).is_file():
                errors.append(f"文本编码器目录缺少 {name}: {te_dir}")
        if not any(te_dir.glob("*.safetensors")):
            errors.append(f"文本编码器目录缺少权重文件（*.safetensors）: {te_dir}")
        expected_hidden = spec.get("te_hidden_size")
        config_file = te_dir / "config.json"
        if expected_hidden and config_file.is_file():
            try:
                actual_hidden = json.loads(config_file.read_text(encoding="utf-8")).get("hidden_size")
            except (json.JSONDecodeError, OSError):
                actual_hidden = None
            if isinstance(actual_hidden, int) and actual_hidden != expected_hidden:
                errors.append(
                    f"文本编码器与变体不匹配：{te_dir} 的 hidden_size={actual_hidden}，"
                    f"变体 {variant} 期望 {spec.get('text_encoder')}（hidden_size={expected_hidden}），"
                    "请更换为与变体对应的文本编码器"
                )

    images: list[Path] = []
    for entry in datasets:
        folder = Path(str(entry.get("folder_path", "")))
        found = _dataset_images(folder)
        images.extend(found)
        if not found:
            errors.append(f"数据集目录没有图片: {folder}")
        control_dirs = [Path(str(d)) for d in entry.get("control_path") or []]
        existing_controls: list[Path] = []
        for control_dir in control_dirs:
            if not control_dir.is_dir():
                errors.append(f"参考图目录不存在: {control_dir}")
            else:
                existing_controls.append(control_dir)
        if existing_controls and found:
            control_stems = {
                d: {p.stem for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS}
                for d in existing_controls
            }
            missing: list[str] = []
            for image in found:
                for control_dir in existing_controls:
                    if image.stem not in control_stems[control_dir]:
                        missing.append(f"{image.name} → {control_dir}")
            if missing:
                shown = "、".join(missing[:3])
                errors.append(
                    f"参考图与训练图同名配对缺失 {len(missing)} 项（如 {shown}）："
                    "图像编辑训练要求每张训练图在各参考图目录中有同名图片"
                )
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

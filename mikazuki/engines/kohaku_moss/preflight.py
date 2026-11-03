"""Asset checks that do not import the ML runtime."""
from pathlib import Path

from mikazuki.engines.moss.comfy import (
    materialize_comfy_encoders,
    validate_comfy_components,
)

from .adapter import adapt_config


def check_inputs(adapted, *, materialize: bool = True):
    values = adapted.values
    errors = []
    weights = Path(values["WEIGHTS"])
    dataset = Path(values["DATASETS"][0]["path"])
    output = Path(values["OUTPUT_DIR"])
    facts = {
        "weights": str(weights),
        "dataset": str(dataset),
        "output_dir": str(output),
        "total_steps": values["STEPS"],
        "model_input_mode": adapted.model_input_mode,
    }

    if adapted.model_input_mode == "comfyui_files":
        comfy_paths = dict(adapted.comfy_paths or {})
        variant = values.get("VARIANT", "base")
        if variant == "sft" and not comfy_paths.get("sft_dit_path"):
            comfy_paths["sft_dit_path"] = comfy_paths.get("dit_path", "")
        try:
            comfy_facts = validate_comfy_components(
                comfy_paths,
                model=variant,
                needs_text=True,
                needs_vae=True,
            )
            facts.update(comfy_facts)
            if materialize and adapted.staging_root:
                resolved = {
                    key: comfy_facts[key]
                    for key in ("text_encoder_path", "vae_path", "tokenizer_path")
                }
                staging = materialize_comfy_encoders(
                    resolved,
                    staging_root=Path(adapted.staging_root),
                )
                facts["staging_root"] = str(staging)
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
    else:
        if not weights.exists():
            errors.append(f"MOSS-Image 权重路径不存在：{weights}")
        elif weights.is_dir():
            if not (weights / "transformer").exists():
                errors.append(f"MOSS-Image 权重目录缺少 transformer/：{weights}")
            te_root = Path(values["TEXT_ENCODER"]) if values.get("TEXT_ENCODER") else weights
            te_dir = te_root / "text_encoder" if (te_root / "text_encoder").exists() else te_root
            vae_root = Path(values["VAE"]) if values.get("VAE") else weights / "vae"
            vae_dir = vae_root / "vae" if (vae_root / "vae").exists() else vae_root
            if not te_dir.exists() or not (te_dir / "config.json").exists():
                errors.append(f"MOSS-Image 权重目录缺少 text_encoder/：{te_root / 'text_encoder'}")
            if not vae_dir.exists() or not (vae_dir / "config.json").exists():
                errors.append(f"MOSS-Image 权重目录缺少 vae/：{vae_dir}")

    if not dataset.is_dir():
        errors.append(f"训练数据集目录不存在：{dataset}")
    else:
        images = [path for path in dataset.rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
        if not images:
            errors.append(f"训练数据集未找到图片：{dataset}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": adapted.warnings,
        "facts": facts,
    }


def run_preflight(config, runtime, *, materialize: bool = False):
    return check_inputs(adapt_config(config, runtime), materialize=materialize)

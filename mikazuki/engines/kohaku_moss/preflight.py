"""Asset checks that do not import the ML runtime."""
from pathlib import Path

from .adapter import adapt_config


def check_inputs(adapted):
    values = adapted.values
    errors = []
    weights = Path(values["WEIGHTS"])
    dataset = Path(values["DATASETS"][0]["path"])
    if not weights.exists():
        errors.append(f"MOSS-Image 权重路径不存在：{weights}")
    elif weights.is_dir():
        for name in ("transformer", "text_encoder", "vae"):
            if not (weights / name).exists():
                errors.append(f"MOSS-Image 权重目录缺少 {name}/：{weights}")
    if not dataset.is_dir():
        errors.append(f"训练数据集目录不存在：{dataset}")
    else:
        images = [path for path in dataset.rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
        if not images:
            errors.append(f"训练数据集未找到图片：{dataset}")
    output = Path(values["OUTPUT_DIR"])
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": adapted.warnings,
        "facts": {"weights": str(weights), "dataset": str(dataset), "output_dir": str(output), "total_steps": values["STEPS"]},
    }


def run_preflight(config, runtime):
    return check_inputs(adapt_config(config, runtime))

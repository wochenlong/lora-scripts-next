"""Read-only preflight: parse form values and inspect local headers, never spawn."""
from pathlib import Path
from collections import Counter
import math

from .adapter import adapt_config
from .inputs import check_output, validate_cache, validate_models


def batch_facts(adapted):
    """Predict native target sizes without importing any ML package."""
    from PIL import Image
    from .inputs import source_pairs, LATENT_RE
    shapes = []
    if adapted.run_preprocess:
        cap = adapted.cache["resolution"] ** 2
        for image, _hash in source_pairs(adapted.cache["src"]).values():
            with Image.open(image) as opened:
                width, height = opened.size
            if width % 16 == height % 16 == 0 and width * height <= cap * 1.10:
                shapes.append((width, height))
                continue
            area, aspect = min(cap, width * height), width / height
            w = max(16, min(round(math.sqrt(area * aspect) / 16) * 16, width // 16 * 16))
            h = max(16, min(round(math.sqrt(area / aspect) / 16) * 16, height // 16 * 16))
            shapes.append((w, h))
    else:
        for path in Path(adapted.train["cache"]).glob("*.moss_latent.safetensors"):
            match = LATENT_RE.match(path.name)
            if match:
                shapes.append((int(match["w"]), int(match["h"])))
    counts = Counter(shapes)
    batch_size = adapted.train["batch_size"]
    return {"steps_per_epoch": sum(math.ceil(n / batch_size) for n in counts.values()),
            "bucket_count": len(counts), "partial_batches_per_epoch": sum(n % batch_size != 0 for n in counts.values()),
            "batch_size": batch_size, "drop_last": False, "gradient_accumulation_steps": 1}


def check_inputs(adapted):
    facts = {**validate_models(adapted), **validate_cache(adapted)}
    output = Path(adapted.train["output"])
    parent = output.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if not parent.is_dir():
        raise ValueError(f"output_dir: parent is not a directory / 父路径不是目录: {parent}")
    check_output(output)
    samples = facts["dataset_pairs"] if adapted.run_preprocess else facts["cache_pairs"]
    epochs, max_steps = adapted.train["epochs"], adapted.train["max_steps"]
    batches = batch_facts(adapted)
    total = epochs * batches["steps_per_epoch"]
    if max_steps:
        total = min(total, max_steps) if epochs else max_steps
    facts.update(total_steps=total, **batches)
    return facts


def run_preflight(config, runtime):
    try:
        adapted = adapt_config(config, runtime)
        facts = check_inputs(adapted)
        return {"ok": True, "errors": [], "warnings": adapted.warnings, "facts": facts}
    except (ValueError, OSError) as exc:
        return {"ok": False, "errors": [str(exc)], "warnings": [], "facts": {}}

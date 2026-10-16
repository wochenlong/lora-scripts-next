"""Read-only preflight: parse form values and inspect local headers, never spawn."""
from pathlib import Path

from .adapter import adapt_config
from .inputs import check_output, validate_cache, validate_models


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
    total = epochs * samples
    if max_steps:
        total = min(total, max_steps) if epochs else max_steps
    facts.update(total_steps=total, batch_size=1)
    return facts


def run_preflight(config, runtime):
    try:
        adapted = adapt_config(config, runtime)
        facts = check_inputs(adapted)
        return {"ok": True, "errors": [], "warnings": adapted.warnings, "facts": facts}
    except (ValueError, OSError) as exc:
        return {"ok": False, "errors": [str(exc)], "warnings": [], "facts": {}}

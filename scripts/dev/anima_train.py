from __future__ import annotations

import runpy
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROOT_STR = str(ROOT)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

from mikazuki.anima_backend.adapter import adapt_anima_config
from mikazuki.anima_backend.upstream import (
    load_toml_file,
    prefer_upstream_imports,
    resolve_upstream_path,
    upstream_entrypoint,
    verify_pinned_commit,
)

FINETUNE_ENTRYPOINT = "anima_train.py"


def _format_toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_toml_value(item) for item in value) + "]"
    escaped = str(value).replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def _dump_flat_toml(config: dict) -> str:
    return "\n".join(f"{key} = {_format_toml_value(value)}" for key, value in config.items()) + "\n"


def _rewrite_config_file(argv: list[str]) -> Path | None:
    if "--config_file" not in argv:
        return None
    index = argv.index("--config_file")
    if index + 1 >= len(argv):
        return None

    original = Path(argv[index + 1])
    config = load_toml_file(original)
    adapted, warnings = adapt_anima_config(config, finetune=True)
    for warning in warnings:
        print(f"[Anima backend compatibility] {warning}", file=sys.stderr)

    adapted_path = original.with_name(f"{original.stem}-sd-scripts.toml")
    adapted_path.write_text(_dump_flat_toml(adapted), encoding="utf-8")
    argv[index + 1] = str(adapted_path)
    return adapted_path


def main() -> None:
    root = ROOT
    verify_pinned_commit(root)
    upstream_path = resolve_upstream_path(root)
    prefer_upstream_imports(upstream_path)
    _rewrite_config_file(sys.argv)
    script = upstream_entrypoint(upstream_path, FINETUNE_ENTRYPOINT)
    if os.environ.get("ANIMA_BACKEND_WRAPPER_SMOKE") == "1":
        print(f"Anima backend wrapper smoke OK: {script}")
        return
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()

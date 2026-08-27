"""Registry-driven /api/run dispatch.

``/api/run`` resolves ``model_train_type`` through the engine registry and hands
the config to the owning pack's ``run.handle_run``. Adding an engine never
touches ``api.py``: a new pack directory with ``manifest.py`` + ``run.py`` is
picked up automatically.

The five pipeline stages (gate -> adapt -> preflight -> dump -> launch) are the
pack's internal concern; the framework only fixes the entry point.
"""

from __future__ import annotations

from dataclasses import dataclass

from mikazuki.engines import registry


@dataclass(frozen=True)
class RunContext:
    timestamp: str
    autosave_dir: str
    gpu_ids: object = None
    model_train_type: str = ""


def dispatch_run(model_train_type: str, config: dict, ctx: RunContext):
    """Run the owning pack's handler. Returns None when the type is unregistered."""
    hit = registry.resolve_train_type(model_train_type)
    if hit is None:
        return None
    pack, _variant = hit
    handler = pack.import_module("run").handle_run
    return handler(config, ctx)

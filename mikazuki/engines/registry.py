"""Engine pack registry: discovers packs under ``mikazuki/engines/`` and maps
``train_type`` -> (engine, variant) for ``/api/run`` dispatch.

Adding an engine = adding a ``mikazuki/engines/<id>/`` directory with a
``manifest.py``; no changes here or in ``api.py``.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from functools import lru_cache
from types import ModuleType

from mikazuki.engines.manifest import EngineManifest, load_manifest

_PACKAGE = "mikazuki.engines"
_SKIP_DIRS = frozenset({"_template", "__pycache__"})


@dataclass(frozen=True)
class EnginePack:
    manifest: EngineManifest
    package: str

    @property
    def engine_id(self) -> str:
        return self.manifest.engine_id

    def import_module(self, name: str) -> ModuleType:
        return importlib.import_module(f"{self.package}.{name}")


def _iter_pack_packages() -> list[str]:
    package = importlib.import_module(_PACKAGE)
    names = []
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_") or info.name in _SKIP_DIRS:
            continue
        if not info.ispkg:
            continue
        names.append(f"{_PACKAGE}.{info.name}")
    return sorted(names)


@lru_cache(maxsize=1)
def discover_packs() -> dict[str, EnginePack]:
    packs: dict[str, EnginePack] = {}
    for package in _iter_pack_packages():
        manifest = load_manifest(importlib.import_module(f"{package}.manifest"))
        if manifest.engine_id in packs:
            raise ValueError(f"duplicate ENGINE_ID {manifest.engine_id!r} in {package}")
        packs[manifest.engine_id] = EnginePack(manifest=manifest, package=package)
    return packs


def get_pack(engine_id: str) -> EnginePack | None:
    return discover_packs().get(engine_id)


def train_type_map() -> dict[str, tuple[str, str]]:
    """train_type -> (engine_id, variant) across all registered packs."""
    mapping: dict[str, tuple[str, str]] = {}
    for pack in discover_packs().values():
        for train_type, variant in pack.manifest.train_types.items():
            if train_type in mapping:
                raise ValueError(
                    f"train_type {train_type!r} claimed by both {mapping[train_type][0]!r} and {pack.engine_id!r}"
                )
            mapping[train_type] = (pack.engine_id, variant)
    return mapping


def resolve_train_type(train_type: str) -> tuple[EnginePack, str] | None:
    hit = train_type_map().get(train_type)
    if hit is None:
        return None
    engine_id, variant = hit
    pack = get_pack(engine_id)
    if pack is None:
        return None
    return pack, variant


def reset_cache() -> None:
    discover_packs.cache_clear()

"""kohya builtin engine routes (mounted at /api/engines/kohya/*).

Builtin packs are always ready and have no install/repair/uninstall pipeline;
the generic engine router turns missing handlers into clear errors.
"""

from mikazuki.app.models import APIResponseSuccess
from mikazuki.engines.kohya.manifest import TRAIN_TYPES


async def status():
    return APIResponseSuccess(data={
        "state": "ready",
        "kind": "builtin",
        "feature_enabled": True,
        "train_types": sorted(TRAIN_TYPES),
    })

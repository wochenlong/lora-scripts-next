"""Engine pack manifest contract (frozen 2026-08, issues #301/#302).

Every ``mikazuki/engines/<id>/manifest.py`` data module must define:

- ``ENGINE_ID``: unique engine id, also the route segment (``/api/engines/<id>/``).
- ``KIND``: ``"plugin"`` (installable, isolated venv) or ``"builtin"`` (ships with
  the main environment, always ready — e.g. kohya).
- ``TRAIN_TYPES``: mapping of UI ``train_type`` -> variant name. This is the
  ``/api/run`` dispatch key; the registry builds the reverse lookup.
- ``UPSTREAM``: pinned upstream source. Download priority is ``zip`` (offline
  distribution bundle, currently realized as ``vendor/vendor-bundle.*`` — see
  ``mikazuki/engines/VENDOR_BUNDLE.md``) -> ``github`` -> ``gitee`` fallback;
  ``repo`` and ``commit`` always pin the version regardless of channel::

      UPSTREAM = {
          "repo": "kohya-ss/musubi-tuner",
          "commit": "<pinned sha or '' when the config file decides>",
          "zip": None,          # optional distribution bundle URL
          "github": "https://github.com/kohya-ss/musubi-tuner.git",
          "gitee": None,        # optional fallback mirror
      }

- ``FEATURE_FLAG_ENV``: maintainer kill-switch env var name (``=0`` hides the engine).
  May be empty for builtin packs that cannot be disabled.
- ``CAPABILITIES``: free-form capability matrix (model families x tasks x variants).
- ``PATCHES``: list of patch entries applied to the upstream snapshot at install
  time (empty for builtin packs).
- ``REQUIRES`` / ``SLIM_SUPPORTED``: reserved placeholders for the cloud slim
  install mode; only ``isolated`` installs are implemented for now.

``load_manifest(package)`` validates a pack's manifest module and returns an
``EngineManifest``. Unknown extra keys in ``UPSTREAM``/``CAPABILITIES`` are
tolerated; missing required fields fail loudly at registry scan time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import ModuleType

KIND_PLUGIN = "plugin"
KIND_BUILTIN = "builtin"
KINDS = frozenset({KIND_PLUGIN, KIND_BUILTIN})

_UPSTREAM_KEYS = frozenset({"repo", "commit", "zip", "github", "gitee"})


@dataclass(frozen=True)
class EngineManifest:
    engine_id: str
    kind: str
    train_types: dict[str, str]
    upstream: dict[str, str | None]
    feature_flag_env: str
    capabilities: dict = field(default_factory=dict)
    patches: list = field(default_factory=list)
    requires: dict = field(default_factory=dict)
    slim_supported: bool = False


def _require(module: ModuleType, name: str):
    value = getattr(module, name, None)
    if value is None:
        raise ValueError(f"engine manifest {module.__name__} is missing {name}")
    return value


def load_manifest(module: ModuleType) -> EngineManifest:
    engine_id = str(_require(module, "ENGINE_ID")).strip()
    if not engine_id:
        raise ValueError(f"engine manifest {module.__name__} has empty ENGINE_ID")
    kind = str(_require(module, "KIND")).strip()
    if kind not in KINDS:
        raise ValueError(f"engine manifest {module.__name__} has unknown KIND={kind!r}")
    train_types = dict(_require(module, "TRAIN_TYPES"))
    if not train_types:
        raise ValueError(f"engine manifest {module.__name__} has empty TRAIN_TYPES")
    upstream = dict(_require(module, "UPSTREAM"))
    missing = _UPSTREAM_KEYS - upstream.keys()
    if missing:
        raise ValueError(f"engine manifest {module.__name__} UPSTREAM missing keys: {sorted(missing)}")
    if not str(upstream.get("repo") or "").strip():
        raise ValueError(f"engine manifest {module.__name__} UPSTREAM.repo is required for version pinning")
    return EngineManifest(
        engine_id=engine_id,
        kind=kind,
        train_types=train_types,
        upstream=upstream,
        feature_flag_env=str(getattr(module, "FEATURE_FLAG_ENV", "") or "").strip(),
        capabilities=dict(getattr(module, "CAPABILITIES", {}) or {}),
        patches=list(getattr(module, "PATCHES", []) or []),
        requires=dict(getattr(module, "REQUIRES", {}) or {}),
        slim_supported=bool(getattr(module, "SLIM_SUPPORTED", False)),
    )

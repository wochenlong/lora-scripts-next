"""ai-toolkit run.py driver: apply pack-side overrides, then hand off to upstream.

Runs inside the extension venv with cwd = toolkit source root (launcher
contract). Currently injects the Klein TE path override — upstream keeps
``flux2_klein_te_path`` as a class attribute with no config key, so we set it
before the model classes are instantiated. Remove once upstream grows a config
key (or the engines patch applier lands and this becomes a .diff).
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: driver.py <config.yaml> [run.py args...]")
    root = Path.cwd().resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    te_path = os.environ.get("AI_TOOLKIT_TE_PATH", "").strip()
    if te_path:
        from extensions_built_in.diffusion_models.flux2 import Flux2Klein4BModel, Flux2Klein9BModel

        Flux2Klein4BModel.flux2_klein_te_path = te_path
        Flux2Klein9BModel.flux2_klein_te_path = te_path

    sys.argv = ["run.py", *sys.argv[1:]]
    runpy.run_path(str(root / "run.py"), run_name="__main__")


if __name__ == "__main__":
    main()

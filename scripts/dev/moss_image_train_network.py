"""Thin entrypoint for the vendored Kohya MOSS-Image trainer."""

import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "vendor" / "sd-scripts"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

runpy.run_path(str(VENDOR / "moss_image_train_network.py"), run_name="__main__")

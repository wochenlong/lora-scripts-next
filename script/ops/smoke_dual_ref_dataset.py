#!/usr/bin/env python3
"""Smoke-test ControlNetDataset dual-reference pairing without full training."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "vendor" / "sd-scripts"
sys.path.insert(0, str(VENDOR))

from library.config_util import ConfigSanitizer, BlueprintGenerator, generate_dataset_group_by_blueprint
import argparse

DATASET_TOML = """
[general]
caption_extension = ".txt"

[[datasets]]
resolution = [512, 512]
batch_size = 1
enable_bucket = true
min_bucket_reso = 256
max_bucket_reso = 1024
bucket_reso_steps = 64

[[datasets.subsets]]
image_dir = "./data/edit3/target"
conditioning_data_dir = "./data/edit3/reference"
conditioning_multi_reference = true
conditioning_reference_count = 2
"""


def main() -> None:
    user_config = __import__("toml").loads(DATASET_TOML)
    for subset in user_config["datasets"][0]["subsets"]:
        for key in ("image_dir", "conditioning_data_dir"):
            subset[key] = str((ROOT / subset[key].lstrip("./")).resolve()).replace("\\", "/")

    sanitizer = ConfigSanitizer(True, True, True, False)
    gen = BlueprintGenerator(sanitizer)
    blueprint = gen.generate(user_config, argparse.Namespace())
    train_ds, _ = generate_dataset_group_by_blueprint(blueprint.dataset_group)
    ds = train_ds.datasets[0]
    infos = list(ds.image_data.values())
    if not infos:
        raise SystemExit("no images in dataset")
    info = infos[0]
    paths = ds._conditioning_paths_for_info(info)
    if len(paths) != 2:
        raise SystemExit(f"expected 2 conditioning paths, got {len(paths)}: {paths}")
    print("conditioning paths:", paths)
    print("dual-reference dataset pairing smoke OK")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Reorganize flat data/edit3 into target/ + reference/<stem>/ for dual-reference smoke tests."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _pick_files(src: Path) -> tuple[Path | None, list[Path]]:
    images = sorted(
        [p for p in src.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES],
        key=lambda p: p.name,
    )
    target = None
    refs: list[Path] = []
    for path in images:
        name = path.stem
        if name in {"目标", "target", "edit_target"}:
            target = path
        elif name.startswith("参考") or name.startswith("ref"):
            refs.append(path)
    if target is None and images:
        # fallback: largest file as target, rest as refs
        images_by_size = sorted(images, key=lambda p: p.stat().st_size, reverse=True)
        target = images_by_size[0]
        refs = [p for p in images if p != target]
    refs = sorted(refs, key=lambda p: p.name)[:2]
    return target, refs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("data/edit3"),
        help="Flat directory with target + reference images",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Output root (default: same as --src)",
    )
    parser.add_argument("--stem", default="sample1", help="Target/reference subdirectory stem")
    args = parser.parse_args()

    src = args.src.resolve()
    dest = (args.dest or src).resolve()
    target_dir = dest / "target"
    ref_dir = dest / "reference" / args.stem
    target_dir.mkdir(parents=True, exist_ok=True)
    ref_dir.mkdir(parents=True, exist_ok=True)

    target_src, ref_srcs = _pick_files(src)
    if target_src is None:
        raise SystemExit(f"No images found in {src}")
    if len(ref_srcs) < 2:
        raise SystemExit(f"Need at least 2 reference images in {src}, found {len(ref_srcs)}")

    target_dst = target_dir / f"{args.stem}{target_src.suffix.lower()}"
    shutil.copy2(target_src, target_dst)
    caption = target_dst.with_suffix(".txt")
    if not caption.exists() or caption.read_text(encoding="utf-8").strip() == "":
        caption.write_text("anima edit sample", encoding="utf-8")

    for idx, ref_src in enumerate(ref_srcs[:2], start=1):
        ref_dst = ref_dir / f"{idx}{ref_src.suffix.lower()}"
        shutil.copy2(ref_src, ref_dst)

    print(f"target: {target_dst}")
    print(f"references: {ref_dir / ('1' + ref_srcs[0].suffix.lower())}, {ref_dir / ('2' + ref_srcs[1].suffix.lower())}")


if __name__ == "__main__":
    main()

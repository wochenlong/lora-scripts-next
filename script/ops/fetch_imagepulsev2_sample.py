#!/usr/bin/env python3
"""Download a small sample from ImagePulseV2-Edit-Merge (2 refs -> merged target)."""
from __future__ import annotations

import json
import shutil
import tarfile
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO = "DiffSynth-Studio/ImagePulseV2-Edit-Merge"
TAR_FILE = "data/1775727894710656047.tar.gz"
LIMIT = 100
OUT = Path(__file__).resolve().parents[2] / "data" / "imagepulsev2-edit-merge-100"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tar_path = Path(
        hf_hub_download(REPO, TAR_FILE, repo_type="dataset")
    )
    work = OUT / "_extract"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    with tarfile.open(tar_path, "r:gz") as tf:
        tf.extractall(work)

    # Discover layout: look for metadata and image triplets
    meta_files = list(work.rglob("metadata.*"))
    image_exts = {".png", ".jpg", ".jpeg", ".webp"}
    all_images = [p for p in work.rglob("*") if p.suffix.lower() in image_exts]

    manifest: list[dict] = []
    if meta_files:
        meta_path = meta_files[0]
        if meta_path.suffix == ".jsonl":
            rows = [json.loads(line) for line in meta_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        elif meta_path.suffix == ".json":
            rows = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(rows, dict):
                rows = rows.get("data") or rows.get("samples") or [rows]
        else:
            import csv

            rows = list(csv.DictReader(meta_path.open(encoding="utf-8")))
        base = meta_path.parent
        for i, row in enumerate(rows[:LIMIT]):
            sample_id = f"{i:04d}"
            sample_dir = OUT / sample_id
            ref_dir = sample_dir / "reference"
            target_dir = sample_dir / "target"
            ref_dir.mkdir(parents=True)
            target_dir.mkdir(parents=True)
            keys = list(row.keys())
            # Heuristic: image_1, image_2, merged / target / output
            ref_keys = [k for k in keys if "1" in k.lower() or "ref" in k.lower() or "input" in k.lower()]
            target_keys = [k for k in keys if any(x in k.lower() for x in ("merge", "target", "output", "result"))]
            if len(ref_keys) < 2:
                ref_keys = [k for k in keys if k not in target_keys and "prompt" not in k.lower()][:2]
            if not target_keys:
                target_keys = [k for k in keys if k not in ref_keys and "prompt" not in k.lower()][-1:]
            refs = []
            for rk in ref_keys[:2]:
                src = base / str(row[rk])
                if src.is_file():
                    dst = ref_dir / f"{len(refs)+1}{src.suffix.lower()}"
                    shutil.copy2(src, dst)
                    refs.append(str(dst.relative_to(OUT)).replace("\\", "/"))
            for tk in target_keys[:1]:
                src = base / str(row[tk])
                if src.is_file():
                    dst = target_dir / f"merged{src.suffix.lower()}"
                    shutil.copy2(src, dst)
                    prompt = row.get("prompt") or row.get("caption") or ""
                    if prompt:
                        (target_dir / "merged.txt").write_text(str(prompt), encoding="utf-8")
                    manifest.append(
                        {
                            "id": sample_id,
                            "refs": refs,
                            "target": str(dst.relative_to(OUT)).replace("\\", "/"),
                            "prompt": prompt,
                            "raw_row": row,
                        }
                    )
    else:
        # Fallback: group images by parent folder name patterns
        by_parent: dict[str, list[Path]] = {}
        for img in all_images:
            by_parent.setdefault(img.parent.name, []).append(img)
        count = 0
        for parent, imgs in sorted(by_parent.items()):
            if count >= LIMIT:
                break
            if len(imgs) < 3:
                continue
            imgs = sorted(imgs)[:3]
            sample_id = f"{count:04d}"
            sample_dir = OUT / sample_id
            ref_dir = sample_dir / "reference"
            target_dir = sample_dir / "target"
            ref_dir.mkdir(parents=True)
            target_dir.mkdir(parents=True)
            for j, src in enumerate(imgs[:2]):
                shutil.copy2(src, ref_dir / f"{j+1}{src.suffix.lower()}")
            shutil.copy2(imgs[2], target_dir / f"merged{imgs[2].suffix.lower()}")
            manifest.append({"id": sample_id, "parent": parent, "files": [p.name for p in imgs[:3]]})
            count += 1

    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "source": f"https://modelscope.cn/datasets/DiffSynth-Studio/ImagePulseV2-Edit-Merge",
                "tar": TAR_FILE,
                "count": len(manifest),
                "layout": "reference/1.* + reference/2.* -> target/merged.*",
                "samples": manifest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    shutil.rmtree(work, ignore_errors=True)
    print(f"Wrote {len(manifest)} samples to {OUT}")


if __name__ == "__main__":
    main()

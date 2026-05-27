#!/usr/bin/env python3
"""Register one curated Anima Edit showcase case (AI ref + caption, no GT required)."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = ROOT / "data" / "anima-edit-showcase-curated"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, help="Case id, e.g. case01")
    parser.add_argument("--ref", type=Path, required=True, help="Reference image from AI or paintover")
    parser.add_argument("--caption-file", type=Path, required=True, help="Full edit caption (.txt)")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--title", default="", help="Short Chinese title for manifest")
    args = parser.parse_args()

    root = args.root.resolve()
    ref_dir = root / "reference"
    prompt_dir = root / "prompts"
    ref_dir.mkdir(parents=True, exist_ok=True)
    prompt_dir.mkdir(parents=True, exist_ok=True)

    case_id = args.id.strip()
    ref_src = args.ref.resolve()
    if not ref_src.is_file():
        raise SystemExit(f"Reference not found: {ref_src}")

    suffix = ref_src.suffix.lower() or ".png"
    ref_dst = ref_dir / f"{case_id}-ref{suffix}"
    if ref_src.resolve() != ref_dst.resolve():
        shutil.copy2(ref_src, ref_dst)

    caption = args.caption_file.read_text(encoding="utf-8").strip()
    if not caption:
        raise SystemExit("Caption file is empty")
    (prompt_dir / f"{case_id}.txt").write_text(caption, encoding="utf-8")

    manifest_path = root / "manifest.json"
    manifest: dict = {"cases": []}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = manifest.setdefault("cases", [])
    cases = [c for c in cases if c.get("id") != case_id]
    cases.append(
        {
            "id": case_id,
            "title": args.title or case_id,
            "reference": ref_dst.relative_to(ROOT).as_posix(),
            "caption_file": (prompt_dir / f"{case_id}.txt").relative_to(ROOT).as_posix(),
        }
    )
    manifest["cases"] = cases
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"registered {case_id} -> {root}")


if __name__ == "__main__":
    main()

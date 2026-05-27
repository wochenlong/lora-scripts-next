#!/usr/bin/env python3
"""Download showcase reference images via invoke-aisp.ps1 (key in ~/.gbits/)."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
URI = "http://aitools.g-bits.com/aiserviceproxy/api/v1/image/generate"
REF_DIR = ROOT / "data/anima-edit-showcase-curated/reference"
SCRATCH = ROOT / "script/scratch"
KEY_FILE = Path.home() / ".gbits/aiserviceproxy_api_key.txt"


def _api_key() -> str:
    if os.environ.get("AISERVICEPROXY_API_KEY"):
        return os.environ["AISERVICEPROXY_API_KEY"].strip()
    if KEY_FILE.is_file():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    raise SystemExit(
        "Set AISERVICEPROXY_API_KEY or create ~/.gbits/aiserviceproxy_api_key.txt"
    )


def _image_url(payload: dict) -> str:
    data = payload.get("data") or {}
    for key in ("url", "image_url", "cos_url"):
        if isinstance(data.get(key), str) and data[key].startswith("http"):
            return data[key]
    images = data.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, str) and first.startswith("http"):
            return first
        if isinstance(first, dict):
            for key in ("url", "image_url"):
                if isinstance(first.get(key), str):
                    return first[key]
    raise KeyError(f"no image url in response: {list(data.keys())}")


def _output_path(case_id: str) -> Path:
    """case02 -> single-ref; dual01-1 -> dual-curated/reference/dual01/1.png."""
    if case_id.rsplit("-", 1)[-1].isdigit() and case_id.count("-") >= 1:
        stem, idx = case_id.rsplit("-", 1)
        out = ROOT / "data/anima-edit-showcase-dual-curated/reference" / stem / f"{idx}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        return out
    out = REF_DIR / f"{case_id}-ref.png"
    REF_DIR.mkdir(parents=True, exist_ok=True)
    return out


def generate(case_id: str) -> None:
    body_path = SCRATCH / f"aisp-{case_id}-ref.json"
    if not body_path.is_file():
        raise SystemExit(f"missing body: {body_path}")
    body_bytes = body_path.read_bytes()
    req = urllib.request.Request(
        URI,
        data=body_bytes,
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload.get("success"):
        raise SystemExit(f"AISP error {case_id}: {payload}")
    url = _image_url(payload)
    out = _output_path(case_id)
    urllib.request.urlretrieve(url, out)
    print(f"saved {out} ({out.stat().st_size} bytes)")


def main() -> None:
    ids = sys.argv[1:] or ["case02", "case03", "case04"]
    for case_id in ids:
        generate(case_id)


if __name__ == "__main__":
    main()

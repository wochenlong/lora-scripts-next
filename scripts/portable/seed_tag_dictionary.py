#!/usr/bin/env python3
"""Seed the public dictionary during a Release update, preserving existing data."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mikazuki.tag_translation.dictionary_bundle import (  # noqa: E402
    DictionaryBundleError,
    seed_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = seed_bundle(args.source, args.target)
    except (DictionaryBundleError, OSError) as error:
        print(f"Tag dictionary Release seed failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

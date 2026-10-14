#!/usr/bin/env python3
"""Prepare the locked public Tag dictionary for offline portable distributions.

Runs with Python -S: no runtime, aiohttp, Pillow, settings, caches, or model
services are loaded. Existing bundles are verified before reuse; --force only
replaces them after a complete replacement passes the same release lock.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mikazuki.tag_translation.dictionary_bundle import (  # noqa: E402
    DictionaryBundleError, prepare_bundle, validate_database, verify_bundle, verify_translation_assets,
)


async def prefetch(directory: Path, if_missing: bool, force: bool, *,
                   verify_only=False, strict=False, manifest=None) -> int:
    try:
        if verify_only:
            status = await asyncio.to_thread(verify_bundle, directory, manifest)
        elif if_missing and not strict and not force and os.path.lexists(directory / "tag.sqlite"):
            # Existing user installations may contain a newer dictionary or only
            # the legacy two files. Retain a structurally valid user database;
            # every release build and verify-only still uses the locked bundle.
            count = await asyncio.to_thread(validate_database, directory / "tag.sqlite")
            status = {"state": "ready", "installed": True, "row_count": count,
                      "downloaded": False, "preserved": True}
        else:
            status = await asyncio.to_thread(prepare_bundle, directory,
                                           if_missing=if_missing, force=force, manifest=manifest)
        if strict:
            if directory.name != "danbooru":
                raise DictionaryBundleError("Strict packages must use the danbooru directory name")
            status = await asyncio.to_thread(verify_translation_assets, directory.parent, manifest)
        print(json.dumps({"status": "success", "dictionary": status}, ensure_ascii=True))
        return 0
    except (DictionaryBundleError, OSError, ValueError) as error:
        print(f"tag dictionary failed: {error}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    translation_root = Path(os.environ.get("MIKAZUKI_TAG_TRANSLATION_ROOT", str(REPO_ROOT / "assets/tag_translation")))
    parser.add_argument("--directory", type=Path, default=translation_root / "danbooru")
    parser.add_argument("--if-missing", action="store_true", help="verify and retain an existing bundle without network")
    parser.add_argument("--force", action="store_true", help="download a verified replacement before replacing old files")
    parser.add_argument("--verify-only", action="store_true", help="verify the bundle without any network access")
    parser.add_argument("--strict", action="store_true", help="reject non-public translation assets in the package")
    parser.add_argument("--manifest", type=Path, help="release lock manifest (defaults to the repository asset lock)")
    args = parser.parse_args()
    if args.verify_only and args.force:
        parser.error("--verify-only and --force cannot be combined")
    return asyncio.run(prefetch(args.directory, args.if_missing, args.force,
                                verify_only=args.verify_only, strict=args.strict, manifest=args.manifest))


if __name__ == "__main__":
    raise SystemExit(main())

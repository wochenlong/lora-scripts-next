#!/usr/bin/env python3
"""Download the Danbooru Chinese tag dictionary into the app's translation assets.

Installer and packaging scripts call this so 「中文释义」 works out of the box and
offline, instead of asking the user to press 下载/重试 in the translation settings.

An existing dictionary is kept unless --force is given; the GitHub blob SHA is
verified by the shared service, exactly like the in-app download does. When the
GitHub API is rate limited (easy on shared build machines) the script falls back
to the raw file URL, which needs no API quota.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mikazuki.tag_translation.chinese_dictionary_service import (  # noqa: E402
    ChineseDictionaryService,
    git_blob_sha,
    utc_now,
)
from mikazuki.tag_translation.runtime import DICTIONARY_ROOT  # noqa: E402

MEGABYTE = 1024 * 1024


def _describe(service: ChineseDictionaryService, status: dict) -> str:
    return f"{service.database_path} ({status['size_bytes'] // MEGABYTE} MB, {status['row_count']} rows)"


def _raw_fallback_url(service: ChineseDictionaryService) -> str | None:
    """Derive the raw.githubusercontent.com URL from the service's contents URL."""
    parsed = urlparse(service.contents_url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 5 or parts[0] != "repos" or parts[3] != "contents":
        return None
    owner, repo = parts[1], parts[2]
    file_path = "/".join(parts[4:])
    ref = parse_qs(parsed.query).get("ref", ["main"])[0]
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{file_path}"


def _count_rows(path: Path) -> int:
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0])


def _install_from_raw(service: ChineseDictionaryService, url: str) -> int:
    """Rate-limited API fallback: fetch the raw file, verify it locally, write metadata."""
    target = Path(service.database_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f"{target.name}.download")
    print(f"GitHub API unavailable; downloading directly from {url}")
    try:
        with urlopen(url, timeout=600) as response, open(temp, "wb") as handle:  # noqa: S310 - pinned host
            shutil.copyfileobj(response, handle, length=256 * 1024)
        row_count = _count_rows(temp)
        if row_count <= 0:
            raise RuntimeError("downloaded dictionary has no rows")
        sha = git_blob_sha(str(temp))
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)

    now = utc_now()
    metadata = {
        "installed_sha": sha,
        "remote_sha": sha,
        "download_url": url,
        "remote_size": target.stat().st_size,
        "row_count": row_count,
        "last_checked_at": now,
        "last_updated_at": now,
    }
    Path(service.metadata_path).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"tag dictionary ready: {target} ({target.stat().st_size // MEGABYTE} MB, {row_count} rows)")
    return 0


async def prefetch(directory: Path, if_missing: bool, force: bool) -> int:
    service = ChineseDictionaryService(str(directory))
    status = service.status()
    if if_missing and status["installed"]:
        print(f"tag dictionary already installed: {_describe(service, status)}")
        return 0

    print(f"downloading Danbooru Chinese tag dictionary into {directory} ...")
    service.start_update(force=force)
    status = await service.wait_for_update()
    if status["state"] == "ready" and status["installed"]:
        print(f"tag dictionary ready: {_describe(service, status)}")
        return 0

    print(
        f"tag dictionary download failed: {status.get('error') or status['state']}",
        file=sys.stderr,
    )
    fallback = _raw_fallback_url(service)
    if fallback:
        try:
            return _install_from_raw(service, fallback)
        except Exception as error:  # noqa: BLE001 - report any fallback failure
            print(f"raw fallback failed: {error}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        default=str(DICTIONARY_ROOT),
        help="dictionary directory (defaults to the app's assets/tag_translation/danbooru)",
    )
    parser.add_argument(
        "--if-missing",
        action="store_true",
        help="keep an existing tag.sqlite untouched and skip the network check",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download even when a dictionary already exists",
    )
    args = parser.parse_args()
    return asyncio.run(prefetch(Path(args.directory), args.if_missing, args.force))


if __name__ == "__main__":
    raise SystemExit(main())

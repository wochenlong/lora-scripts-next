# -*- coding: utf-8 -*-
"""Lightweight, non-blocking update check against GitHub Releases."""

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Optional

from mikazuki.log import log

GITHUB_REPO = "wochenlong/lora-scripts-next"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CHECK_INTERVAL_SECONDS = 6 * 3600  # at most once every 6 hours

_cache_file = Path(__file__).resolve().parent.parent / "config" / ".update_cache.json"

_last_result: Optional[dict] = None


def local_version() -> str:
    """Read version from VERSION file, fall back to git describe.

    utf-8-sig: a BOM-prefixed VERSION (PowerShell 5.1 / Notepad default) must
    not leak into the version string (same failure class as the marketplace
    host-version read, rc.4 live acceptance V30).
    """
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    if version_file.is_file():
        v = version_file.read_text(encoding="utf-8-sig").strip()
        if v:
            return v

    import subprocess
    try:
        tag = subprocess.check_output(
            ["git", "-C", str(version_file.parent), "describe", "--tags"],
            stderr=subprocess.DEVNULL,
        ).strip().decode("utf-8")
        return tag
    except Exception:
        return "unknown"


def _version_tuple(v: str):
    """'v2.1.0' / '2.1.0' → (2, 1, 0) for comparison."""
    v = v.lstrip("v").split("-")[0]  # strip leading 'v' and trailing '-N-gXXX'
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) or (0,)


def _load_cache() -> Optional[dict]:
    try:
        if _cache_file.is_file():
            data = json.loads(_cache_file.read_text(encoding="utf-8"))
            if time.time() - data.get("ts", 0) < CHECK_INTERVAL_SECONDS:
                return data
    except Exception:
        pass
    return None


def _save_cache(data: dict):
    try:
        _cache_file.parent.mkdir(parents=True, exist_ok=True)
        _cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def check_update() -> dict:
    """
    Returns dict with keys:
        current, latest, has_update, release_url, release_notes, error
    """
    global _last_result

    current = local_version()
    result = {
        "current": current,
        "latest": None,
        "has_update": False,
        "release_url": f"https://github.com/{GITHUB_REPO}/releases",
        "release_notes": "",
        "error": None,
    }

    cached = _load_cache()
    if cached and cached.get("latest"):
        result["latest"] = cached["latest"]
        result["release_url"] = cached.get("release_url", result["release_url"])
        result["release_notes"] = cached.get("release_notes", "")
        result["has_update"] = _version_tuple(cached["latest"]) > _version_tuple(current)
        _last_result = result
        return result

    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "SD-Trainer"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        latest_tag = data.get("tag_name", "")
        result["latest"] = latest_tag
        result["release_url"] = data.get("html_url", result["release_url"])
        result["release_notes"] = (data.get("body") or "")[:500]
        result["has_update"] = _version_tuple(latest_tag) > _version_tuple(current)

        _save_cache({
            "ts": time.time(),
            "latest": latest_tag,
            "release_url": result["release_url"],
            "release_notes": result["release_notes"],
        })
    except Exception as e:
        result["error"] = str(e)

    _last_result = result
    return result


def get_cached_result() -> Optional[dict]:
    return _last_result


def log_update_notice():
    """Call after check_update(); prints a console notice if update available."""
    r = _last_result
    if not r:
        return
    if r.get("has_update"):
        log.info("=" * 50)
        log.info(f"  New version available: {r['latest']}  (current: {r['current']})")
        log.info(f"  Download: {r['release_url']}")
        log.info("=" * 50)
    elif r.get("error"):
        log.debug(f"Update check failed: {r['error']}")
    else:
        log.info(f"SD-Trainer {r['current']} is up to date.")

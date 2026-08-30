# -*- coding: utf-8 -*-
"""Lightweight, non-blocking update check against GitHub Releases.

Update center policy (stable-only):
- Only non-draft, non-prerelease GitHub Releases
- Tag must match X.Y.Z / vX.Y.Z (no -alpha / -beta / -rc suffix)
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Optional

from mikazuki.log import log

GITHUB_REPO = "wochenlong/lora-scripts-next"
GITHUB_RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=30"
CHECK_INTERVAL_SECONDS = 6 * 3600  # at most once every 6 hours

# Strict stable: 1.2.3 or v1.2.3 only (no pre-release suffix).
_STABLE_TAG_RE = re.compile(r"^v?(\d+\.\d+\.\d+)$", re.IGNORECASE)
_PRE_SUFFIX_RE = re.compile(r"-(alpha|beta|rc|pre|preview)(\.|$)", re.IGNORECASE)

_cache_file = Path(__file__).resolve().parent.parent / "config" / ".update_cache.json"

_last_result: Optional[dict] = None

MODELSCOPE_RELEASE_URL = "https://www.modelscope.cn/datasets/next-lab/release"


def local_version() -> str:
    """Read version from VERSION file, fall back to git describe."""
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    if version_file.is_file():
        v = version_file.read_text(encoding="utf-8").strip()
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


def is_stable_version(v: str) -> bool:
    """True only for plain X.Y.Z / vX.Y.Z (no alpha/beta/rc)."""
    if not v:
        return False
    return bool(_STABLE_TAG_RE.match(v.strip()))


def is_prerelease_version(v: str) -> bool:
    """True when local/current version looks like a pre-release channel."""
    if not v or v == "unknown":
        return False
    if is_stable_version(v):
        return False
    return bool(_PRE_SUFFIX_RE.search(v)) or ("-" in v.lstrip("v"))


def _version_tuple(v: str):
    """'v2.1.0' / '2.1.0-alpha' → (2, 1, 0) for comparison."""
    v = v.lstrip("v").split("-")[0]
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) or (0,)


def _normalize_tag(tag: str) -> str:
    tag = (tag or "").strip()
    m = _STABLE_TAG_RE.match(tag)
    if not m:
        return tag
    return m.group(1)


def _load_cache() -> Optional[dict]:
    try:
        if _cache_file.is_file():
            data = json.loads(_cache_file.read_text(encoding="utf-8"))
            if data.get("channel") != "stable":
                return None
            if time.time() - data.get("ts", 0) < CHECK_INTERVAL_SECONDS:
                return data
    except Exception:
        pass
    return None


def _save_cache(data: dict):
    try:
        _cache_file.parent.mkdir(parents=True, exist_ok=True)
        path_data = dict(data)
        path_data["channel"] = "stable"
        _cache_file.write_text(json.dumps(path_data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _pick_latest_stable(releases: list) -> Optional[dict]:
    """First eligible stable release from GitHub releases list (newest first)."""
    for item in releases:
        if not isinstance(item, dict):
            continue
        if item.get("draft") or item.get("prerelease"):
            continue
        tag = item.get("tag_name") or ""
        if not is_stable_version(tag):
            continue
        return item
    return None


def _has_stable_update(current: str, latest: str) -> bool:
    if not latest or not is_stable_version(latest):
        return False
    latest_t = _version_tuple(latest)
    current_t = _version_tuple(current)
    if is_prerelease_version(current):
        # Preview builds may update to same-base stable (3.0.0-alpha → 3.0.0).
        return latest_t >= current_t
    return latest_t > current_t


def check_update(*, force: bool = False) -> dict:
    """
    Returns dict with keys:
        current, latest, has_update, release_url, release_notes, error,
        channel, modelscope_url, current_is_prerelease
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
        "channel": "stable",
        "modelscope_url": MODELSCOPE_RELEASE_URL,
        "current_is_prerelease": is_prerelease_version(current),
    }

    if not force:
        cached = _load_cache()
        if cached and cached.get("latest"):
            latest = cached["latest"]
            if is_stable_version(str(latest)):
                result["latest"] = _normalize_tag(str(latest))
                result["release_url"] = cached.get("release_url", result["release_url"])
                result["release_notes"] = cached.get("release_notes", "")
                result["has_update"] = _has_stable_update(current, result["latest"])
                _last_result = result
                return result

    try:
        req = urllib.request.Request(
            GITHUB_RELEASES_URL,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Next-Trainer",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if not isinstance(data, list):
            raise ValueError("unexpected GitHub releases payload")

        stable = _pick_latest_stable(data)
        if stable is None:
            result["error"] = "no_stable_release"
        else:
            latest_tag = _normalize_tag(stable.get("tag_name") or "")
            result["latest"] = latest_tag
            result["release_url"] = stable.get("html_url") or result["release_url"]
            result["release_notes"] = (stable.get("body") or "")[:500]
            result["has_update"] = _has_stable_update(current, latest_tag)
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
        log.info(f"  New stable version available: {r['latest']}  (current: {r['current']})")
        log.info(f"  Download: {r['release_url']}")
        log.info("=" * 50)
    elif r.get("error"):
        log.debug(f"Update check failed: {r['error']}")
    else:
        log.info(f"Next Trainer {r['current']} is up to date (stable channel).")

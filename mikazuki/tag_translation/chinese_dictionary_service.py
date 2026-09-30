# This file is adapted from ComfyUI-Autocomplete-Aaalice.
# Source snapshot: 37cabccf9b4d799b7b53a1e2d74f2cd214fe91d0
# License: MIT; see docs/third_party/comfyui-autocomplete-aaalice-MIT.txt.
# Next Trainer changes are tracked in git history.

import asyncio
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import unicodedata
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlparse

import aiohttp


GITHUB_CONTENTS_URL = (
    "https://api.github.com/repos/ffdkj/"
    "ffdkj-Danbooru_Tag-Chinese-English-Translation-Table/contents/tag.sqlite?ref=main"
)
ALLOWED_DOWNLOAD_HOSTS = {"raw.githubusercontent.com", "github.com", "objects.githubusercontent.com"}
USER_AGENT = "Autocomplete-Plus/1.12"
MAX_LOOKUP_ITEMS = 500
MAX_TAG_LENGTH = 200
MAX_SEARCH_LENGTH = 100
MAX_SEARCH_RESULTS = 200


def normalize_tag_key(value):
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return " ".join(normalized.replace("_", " ").split())


def normalize_search_query(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).strip().split())


def escape_like_pattern(value):
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def git_blob_sha(path):
    size = os.path.getsize(path)
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(f"blob {size}\0".encode("ascii"))
    with open(path, "rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class ChineseDictionaryService:
    """Owns the optional ffdkj Simplified Chinese dictionary and its update lifecycle."""

    def __init__(self, directory, session_factory=None, contents_url=GITHUB_CONTENTS_URL):
        self.directory = directory
        self.database_path = os.path.join(directory, "tag.sqlite")
        self.metadata_path = os.path.join(directory, "metadata.json")
        self.session_factory = session_factory or aiohttp.ClientSession
        self.contents_url = contents_url
        self._database_lock = threading.RLock()
        self._task = None
        self._auto_attempted = False
        self._runtime = {
            "state": "ready" if os.path.exists(self.database_path) else "missing",
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "error": None,
        }
        os.makedirs(directory, exist_ok=True)

    def status(self):
        metadata = self._load_metadata()
        installed = os.path.exists(self.database_path)
        state = self._runtime["state"]
        if state not in {"downloading", "checking", "error"}:
            state = "ready" if installed else "missing"
        return {
            "state": state,
            "installed": installed,
            "installed_sha": metadata.get("installed_sha"),
            "remote_sha": metadata.get("remote_sha"),
            "row_count": metadata.get("row_count", 0),
            "size_bytes": os.path.getsize(self.database_path) if installed else 0,
            "last_checked_at": metadata.get("last_checked_at"),
            "last_updated_at": metadata.get("last_updated_at"),
            "downloaded_bytes": self._runtime["downloaded_bytes"],
            "total_bytes": self._runtime["total_bytes"],
            "update_available": bool(
                metadata.get("remote_sha")
                and metadata.get("installed_sha") != metadata.get("remote_sha")
            ),
            "error": self._runtime["error"],
        }

    async def ensure(self, locale):
        normalized = str(locale or "").replace("_", "-").lower()
        chinese_locales = {"zh", "zh-cn", "zh-hans", "zh-tw", "zh-hant", "zh-hk", "zh-mo"}
        if normalized not in chinese_locales:
            return self.status()
        if os.path.exists(self.database_path) or self._auto_attempted:
            return self.status()
        self._auto_attempted = True
        return self.start_update()

    def start_update(self, force=False):
        if self._task and not self._task.done():
            return self.status()
        self._runtime.update(
            state="downloading",
            downloaded_bytes=0,
            total_bytes=0,
            error=None,
        )
        self._task = asyncio.create_task(self._download_and_install(force=force))
        return self.status()

    async def wait_for_update(self):
        if self._task:
            await self._task
        return self.status()

    async def check_update(self):
        if self._task and not self._task.done():
            return self.status()
        self._runtime.update(state="checking", error=None)
        try:
            remote = await self._fetch_remote_metadata()
            metadata = self._load_metadata()
            metadata.update(
                remote_sha=remote["sha"],
                download_url=remote["download_url"],
                remote_size=remote.get("size", 0),
                last_checked_at=utc_now(),
            )
            self._save_metadata(metadata)
            self._runtime["state"] = "ready" if os.path.exists(self.database_path) else "missing"
        except Exception as error:
            self._runtime.update(state="error", error=str(error)[:1000])
        return self.status()

    def lookup(self, tag_names):
        return self._lookup(tag_names, MAX_LOOKUP_ITEMS)

    def lookup_all(self, tag_names):
        return self._lookup(tag_names, None)

    def _lookup(self, tag_names, limit):
        if not os.path.exists(self.database_path):
            return {}
        names = []
        seen = set()
        raw_names = list(tag_names or [])
        if limit is not None:
            raw_names = raw_names[:limit]
        for raw_name in raw_names:
            name = str(raw_name or "").strip()
            if not name or len(name) > MAX_TAG_LENGTH or name in seen:
                continue
            names.append(name)
            seen.add(name)
        if not names:
            return {}
        rows = []
        lookup_keys = {name: normalize_tag_key(name) for name in names}
        variants = list(dict.fromkeys([key for key in lookup_keys.values() if key]))
        with self._database_lock, closing(self._connect_readonly()) as connection:
            for start in range(0, len(variants), 400):
                chunk = variants[start : start + 400]
                placeholders = ",".join("?" for _ in chunk)
                rows.extend(
                    connection.execute(
                        f"""
                        SELECT name, category, cn_name, post_count
                          FROM tags
                         WHERE lower(replace(name, '_', ' ')) IN ({placeholders})
                           AND TRIM(COALESCE(cn_name, '')) != ''
                        """,
                        chunk,
                    ).fetchall()
                )
        by_key = {}
        for row in rows:
            if row["cn_name"].strip().casefold() == row["name"].casefold():
                continue
            key = normalize_tag_key(row["name"])
            previous = by_key.get(key)
            if previous is None or len(row["name"]) > len(previous["name"]):
                by_key[key] = row
        result = {}
        for raw_name, key in lookup_keys.items():
            row = by_key.get(key)
            if row is not None:
                result[raw_name] = {
                    "tag_name": raw_name,
                    "text": row["cn_name"].strip(),
                    "category": int(row["category"] or 0),
                    "post_count": int(row["post_count"] or 0),
                    "origin": "ffdkj",
                }
        return result

    def search(self, query, limit=50):
        value = normalize_search_query(query)
        if not value or len(value) > MAX_SEARCH_LENGTH or not os.path.exists(self.database_path):
            return []
        try:
            bounded_limit = min(max(int(limit), 1), MAX_SEARCH_RESULTS)
        except (TypeError, ValueError):
            bounded_limit = 50
        escaped_value = escape_like_pattern(value)
        contains_pattern = f"%{escaped_value}%"
        prefix_pattern = f"{escaped_value}%"
        with self._database_lock, closing(self._connect_readonly()) as connection:
            rows = connection.execute(
                """
                SELECT name, category, cn_name, post_count
                  FROM tags
                 WHERE cn_name LIKE ? ESCAPE '!'
                   AND TRIM(COALESCE(cn_name, '')) != ''
                 ORDER BY
                    CASE
                        WHEN cn_name = ? THEN 0
                        WHEN cn_name LIKE ? ESCAPE '!' THEN 1
                        ELSE 2
                    END,
                    post_count DESC,
                    name ASC
                 LIMIT ?
                """,
                (contains_pattern, value, prefix_pattern, bounded_limit),
            ).fetchall()
        results = []
        comparable_query = value.casefold()
        for row in rows:
            chinese_name = row["cn_name"].strip()
            if chinese_name.casefold() == row["name"].casefold():
                continue
            comparable_name = chinese_name.casefold()
            match_type = "exact" if comparable_name == comparable_query else (
                "prefix" if comparable_name.startswith(comparable_query) else "contains"
            )
            results.append(
                {
                    "name": row["name"],
                    "category": int(row["category"] or 0),
                    "cn_name": chinese_name,
                    "post_count": int(row["post_count"] or 0),
                    "match_type": match_type,
                    "source": "ffdkj",
                }
            )
        return results

    async def _download_and_install(self, force=False):
        temp_path = None
        try:
            remote = await self._fetch_remote_metadata()
            metadata = self._load_metadata()
            if (
                not force
                and os.path.exists(self.database_path)
                and metadata.get("installed_sha") == remote["sha"]
            ):
                metadata.update(remote_sha=remote["sha"], last_checked_at=utc_now())
                self._save_metadata(metadata)
                self._runtime["state"] = "ready"
                return

            file_descriptor, temp_path = tempfile.mkstemp(
                prefix="tag-",
                suffix=".sqlite.download",
                dir=self.directory,
            )
            os.close(file_descriptor)
            await self._download_file(remote["download_url"], temp_path)
            actual_sha = await asyncio.to_thread(git_blob_sha, temp_path)
            if actual_sha != remote["sha"]:
                raise RuntimeError(
                    f"Downloaded dictionary SHA mismatch: expected {remote['sha']}, got {actual_sha}"
                )
            row_count = await asyncio.to_thread(self._validate_database, temp_path)
            with self._database_lock:
                os.replace(temp_path, self.database_path)
            temp_path = None
            now = utc_now()
            metadata.update(
                installed_sha=remote["sha"],
                remote_sha=remote["sha"],
                download_url=remote["download_url"],
                remote_size=remote.get("size", 0),
                row_count=row_count,
                last_checked_at=now,
                last_updated_at=now,
            )
            self._save_metadata(metadata)
            self._runtime.update(state="ready", error=None)
        except Exception as error:
            self._runtime.update(state="error", error=str(error)[:1000])
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    async def _fetch_remote_metadata(self):
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
        async with self.session_factory(timeout=timeout) as session:
            async with session.get(self.contents_url, headers=headers) as response:
                body = await response.text()
                if response.status != 200:
                    raise RuntimeError(f"GitHub returned HTTP {response.status}: {body[:300]}")
        payload = json.loads(body)
        sha = str(payload.get("sha") or "")
        download_url = str(payload.get("download_url") or "")
        if len(sha) != 40 or not download_url:
            raise RuntimeError("GitHub returned invalid dictionary metadata")
        if urlparse(download_url).hostname not in ALLOWED_DOWNLOAD_HOSTS:
            raise RuntimeError("GitHub returned an untrusted dictionary download URL")
        return {"sha": sha, "download_url": download_url, "size": int(payload.get("size") or 0)}

    async def _download_file(self, url, path):
        timeout = aiohttp.ClientTimeout(total=600)
        headers = {"Accept": "application/octet-stream", "User-Agent": USER_AGENT}
        async with self.session_factory(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise RuntimeError(f"Dictionary download returned HTTP {response.status}")
                self._runtime["total_bytes"] = int(response.headers.get("Content-Length") or 0)
                with open(path, "wb") as target:
                    async for chunk in response.content.iter_chunked(256 * 1024):
                        target.write(chunk)
                        self._runtime["downloaded_bytes"] += len(chunk)

    @staticmethod
    def _validate_database(path):
        with open(path, "rb") as database_file:
            if database_file.read(16) != b"SQLite format 3\x00":
                raise RuntimeError("Downloaded dictionary is not a SQLite database")
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(tags)").fetchall()
            }
            required = {"name", "category", "cn_name", "post_count"}
            if not required.issubset(columns):
                raise RuntimeError("Downloaded dictionary is missing required tags columns")
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            if not quick_check or quick_check[0] != "ok":
                raise RuntimeError("Downloaded dictionary failed SQLite quick_check")
            row_count = int(connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0])
            if row_count <= 0:
                raise RuntimeError("Downloaded dictionary contains no tags")
            return row_count
        finally:
            connection.close()

    def _connect_readonly(self):
        connection = sqlite3.connect(f"file:{self.database_path}?mode=ro", uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _load_metadata(self):
        try:
            with open(self.metadata_path, encoding="utf-8") as source:
                payload = json.load(source)
                return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_metadata(self, metadata):
        file_descriptor, temp_path = tempfile.mkstemp(
            prefix="metadata-",
            suffix=".json.tmp",
            dir=self.directory,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as target:
                json.dump(metadata, target, ensure_ascii=False, indent=2)
                target.write("\n")
            os.replace(temp_path, self.metadata_path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

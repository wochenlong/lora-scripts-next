"""Public dictionary assets for portable builds; standard-library dependencies only.

No runtime, translation settings, cache, or model service is imported here.
All downloads and reused files must match the repository's release lock.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import Request, urlopen

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPOSITORY_ROOT / "scripts/assets/tag-dictionary-manifest.json"
BUNDLE_FILES = ("LICENSE.ffdkj.txt", "source-manifest.json", "metadata.json", "tag.sqlite")
LOCK_FIELDS = ("source_url", "source_commit", "git_blob_sha", "sha256", "size_bytes",
               "row_count", "license", "license_sha256")


class DictionaryBundleError(RuntimeError):
    """A public dictionary asset is missing, invalid, or cannot be installed."""


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise DictionaryBundleError(f"Invalid dictionary JSON: {path.name}") from error
    if not isinstance(value, dict):
        raise DictionaryBundleError(f"Dictionary JSON must be an object: {path.name}")
    return value


def load_manifest(manifest=None) -> dict:
    value = dict(manifest) if isinstance(manifest, dict) else _read_json(
        Path(manifest) if manifest is not None else DEFAULT_MANIFEST)
    for field, length in (("source_commit", 40), ("git_blob_sha", 40), ("sha256", 64), ("license_sha256", 64)):
        if not isinstance(value.get(field), str) or not re.fullmatch(f"[0-9a-f]{{{length}}}", value[field]):
            raise DictionaryBundleError(f"Invalid release lock field: {field}")
    for field in ("size_bytes", "row_count"):
        if type(value.get(field)) is not int or value[field] <= 0:
            raise DictionaryBundleError(f"Invalid release lock field: {field}")
    if value.get("license") != "MIT":
        raise DictionaryBundleError("The release lock must record the dictionary MIT license")
    urls = value.get("download_urls", [value.get("source_url")])
    if not isinstance(urls, list) or not urls:
        raise DictionaryBundleError("The release lock must provide download URLs")
    for url in [value.get("source_url"), *urls]:
        if not isinstance(url, str) or urlparse(url).scheme not in {"http", "https"} or not urlparse(url).hostname:
            raise DictionaryBundleError("The release lock contains an invalid download URL")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha(path) -> str:
    path = Path(path)
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(f"blob {path.stat().st_size}\0".encode("ascii"))
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def validate_database(path) -> int:
    """Validate SQLite without loading application services or writing to the file."""
    path = Path(path)
    try:
        with path.open("rb") as source:
            if source.read(16) != b"SQLite format 3\x00":
                raise DictionaryBundleError("Dictionary is not a SQLite database")
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(tags)")}
            if not {"name", "category", "cn_name", "post_count"}.issubset(columns):
                raise DictionaryBundleError("Dictionary is missing required tags columns")
            if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise DictionaryBundleError("Dictionary failed SQLite quick_check")
            count = int(connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0])
            if count <= 0:
                raise DictionaryBundleError("Dictionary contains no tags")
            return count
    except (OSError, sqlite3.Error) as error:
        raise DictionaryBundleError("Dictionary could not be read or validated") from error


def _verify_database(path: Path, expected: dict) -> int:
    if path.stat().st_size != expected["size_bytes"]:
        raise DictionaryBundleError("Dictionary size does not match the release lock")
    if _sha256(path) != expected["sha256"] or git_blob_sha(path) != expected["git_blob_sha"]:
        raise DictionaryBundleError("Dictionary hash does not match the release lock")
    count = validate_database(path)
    if count != expected["row_count"]:
        raise DictionaryBundleError("Dictionary row count does not match the release lock")
    return count


def _plain_path(path: Path, *, directory=False):
    if path.is_symlink() or (path.exists() and getattr(path.stat(), "st_file_attributes", 0) & 0x400):
        raise DictionaryBundleError(f"Dictionary assets cannot be links: {path.name}")
    if not (path.is_dir() if directory else path.is_file()):
        raise DictionaryBundleError(f"Missing dictionary {'directory' if directory else 'file'}: {path.name}")


def verify_bundle(directory, manifest=None) -> dict:
    directory = Path(directory)
    expected = load_manifest(manifest)
    _plain_path(directory, directory=True)
    if {entry.name for entry in directory.iterdir()} != set(BUNDLE_FILES):
        raise DictionaryBundleError("A dictionary bundle must contain exactly its four public files")
    for name in BUNDLE_FILES:
        _plain_path(directory / name)
    observed = _read_json(directory / "source-manifest.json")
    if any(observed.get(field) != expected[field] for field in LOCK_FIELDS):
        raise DictionaryBundleError("Dictionary source manifest does not match the release lock")
    if set(observed) - {*LOCK_FIELDS, "version", "license_source_url"}:
        raise DictionaryBundleError("Dictionary source manifest contains unexpected fields")
    if "version" in observed and (type(observed["version"]) is not int or observed["version"] != 1):
        raise DictionaryBundleError("Dictionary source manifest version is unsupported")
    if "license_source_url" in observed and observed["license_source_url"] != expected.get("license_source_url"):
        raise DictionaryBundleError("Dictionary license source does not match the release lock")
    if _sha256(directory / "LICENSE.ffdkj.txt") != expected["license_sha256"]:
        raise DictionaryBundleError("Dictionary license does not match the release lock")
    count = _verify_database(directory / "tag.sqlite", expected)
    metadata = _read_json(directory / "metadata.json")
    allowed_metadata = {"installed_sha", "remote_sha", "download_url", "remote_size", "row_count",
                        "last_checked_at", "last_updated_at"}
    if set(metadata) != allowed_metadata:
        raise DictionaryBundleError("Dictionary metadata must contain only the seven public metadata fields")
    for field in ("last_checked_at", "last_updated_at"):
        try:
            if not isinstance(metadata[field], str) or datetime.fromisoformat(metadata[field]).tzinfo is None:
                raise ValueError()
        except ValueError as error:
            raise DictionaryBundleError(f"Invalid dictionary metadata timestamp: {field}") from error
    for key, value in (("installed_sha", expected["git_blob_sha"]), ("remote_sha", expected["git_blob_sha"]),
                       ("download_url", expected["source_url"]), ("remote_size", expected["size_bytes"]),
                       ("row_count", expected["row_count"])):
        if metadata.get(key) != value or type(metadata.get(key)) is not type(value):
            raise DictionaryBundleError(f"Dictionary metadata does not match the release lock: {key}")
    return {"state": "ready", "installed": True, "installed_sha": expected["git_blob_sha"],
            "sha256": expected["sha256"], "row_count": count, "size_bytes": expected["size_bytes"],
            "source_commit": expected["source_commit"], "license": expected["license"], "file_count": 4}


def verify_translation_assets(root, manifest=None) -> dict:
    """Reject all other packaged state by name, without opening its contents."""
    root = Path(root)
    _plain_path(root, directory=True)
    if {entry.name for entry in root.iterdir()} != {"danbooru"}:
        raise DictionaryBundleError("Packaged translation assets may contain only the public danbooru bundle")
    return verify_bundle(root / "danbooru", manifest)


@contextmanager
def _installation_lock(directory: Path):
    """Atomic mkdir serializes both threads and independent installer processes."""
    directory.parent.mkdir(parents=True, exist_ok=True)
    lock = directory.parent / f".{directory.name}-dictionary-install.lock"
    deadline = time.monotonic() + 60
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise DictionaryBundleError("Timed out waiting for the dictionary installation lock")
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.rmdir()


def _write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _commit_stage(stage: Path, target: Path, *, preserve_existing=False) -> bool:
    with _installation_lock(target):
        if preserve_existing and os.path.lexists(target / "tag.sqlite"):
            return False
        target.mkdir(parents=True, exist_ok=True)
        _plain_path(target, directory=True)
        if {entry.name for entry in target.iterdir()} - set(BUNDLE_FILES):
            raise DictionaryBundleError("Dictionary installation target contains unexpected files")
        backup = stage / "backup"
        backup.mkdir()
        replaced = []
        try:
            for name in BUNDLE_FILES:
                old = target / name
                if os.path.lexists(old):
                    _plain_path(old)
                    shutil.copyfile(old, backup / name)
            # Readiness is keyed by the database: publish it after all sidecars.
            for name in BUNDLE_FILES:
                os.replace(stage / name, target / name)
                replaced.append(name)
        except BaseException:
            for name in reversed(replaced):
                if (backup / name).exists():
                    os.replace(backup / name, target / name)
                else:
                    (target / name).unlink(missing_ok=True)
            raise
        return True


def seed_bundle(source_dir, target_dir, manifest=None) -> dict:
    """Seed only a missing database; never read or overwrite an existing user DB."""
    source, target = Path(source_dir), Path(target_dir)
    if os.path.lexists(target / "tag.sqlite"):
        return {"state": "preserved", "installed": True, "seeded": False, "preserved": True}
    expected = load_manifest(manifest)
    verify_bundle(source, expected)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dictionary-seed-", dir=target.parent) as temporary:
        stage = Path(temporary)
        for name in BUNDLE_FILES:
            shutil.copyfile(source / name, stage / name)
        result = verify_bundle(stage, expected)
        installed = _commit_stage(stage, target, preserve_existing=True)
    return {**result, "seeded": installed, "preserved": not installed,
            "state": "ready" if installed else "preserved"}


def _download(url: str, path: Path, expected_size: int):
    headers = {"User-Agent": "Next-Trainer-dictionary-bundle/1", "Accept": "application/octet-stream"}
    if urlparse(url).hostname == "api.github.com":
        headers["Accept"] = "application/vnd.github.raw+json"
    with urlopen(Request(url, headers=headers), timeout=60) as response, path.open("wb") as target:
        length = response.headers.get("Content-Length")
        if length is not None and int(length) != expected_size:
            raise DictionaryBundleError("Downloaded dictionary Content-Length does not match the release lock")
        count = 0
        while chunk := response.read(256 * 1024):
            count += len(chunk)
            if count > expected_size:
                raise DictionaryBundleError("Downloaded dictionary exceeds its locked size")
            target.write(chunk)
        if count != expected_size:
            raise DictionaryBundleError("Downloaded dictionary is truncated")


def prepare_bundle(directory, *, if_missing=False, force=False, manifest=None) -> dict:
    """Download a pinned payload and atomically install only verified public files."""
    target = Path(directory)
    expected = load_manifest(manifest)
    if os.path.lexists(target / "tag.sqlite") and not force:
        return {**verify_bundle(target, expected), "downloaded": False}
    license_path = Path(expected.get("license_file", "docs/third_party/ffdkj-danbooru-tag-table-MIT.txt"))
    if not license_path.is_absolute():
        license_path = REPOSITORY_ROOT / license_path
    if _sha256(license_path) != expected["license_sha256"]:
        raise DictionaryBundleError("Source license does not match the release lock")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dictionary-download-", dir=target.parent) as temporary:
        stage = Path(temporary)
        errors = []
        for url in dict.fromkeys(expected.get("download_urls", [expected["source_url"]])):
            try:
                _download(url, stage / "tag.sqlite", expected["size_bytes"])
                _verify_database(stage / "tag.sqlite", expected)
                break
            except (OSError, ValueError, DictionaryBundleError) as error:
                errors.append(f"{urlparse(url).hostname}: {type(error).__name__}: {error}")
                (stage / "tag.sqlite").unlink(missing_ok=True)
        else:
            raise DictionaryBundleError("Dictionary download failed: " + " | ".join(errors))
        shutil.copyfile(license_path, stage / "LICENSE.ffdkj.txt")
        public_manifest = {field: expected[field] for field in LOCK_FIELDS}
        public_manifest["version"] = expected.get("version", 1)
        if expected.get("license_source_url"):
            public_manifest["license_source_url"] = expected["license_source_url"]
        _write_json(stage / "source-manifest.json", public_manifest)
        now = datetime.now(timezone.utc).isoformat()
        _write_json(stage / "metadata.json", {
            "installed_sha": expected["git_blob_sha"], "remote_sha": expected["git_blob_sha"],
            "download_url": expected["source_url"], "remote_size": expected["size_bytes"],
            "row_count": expected["row_count"], "last_checked_at": now, "last_updated_at": now,
        })
        result = verify_bundle(stage, expected)
        installed = _commit_stage(stage, target, preserve_existing=if_missing and not force)
    if not installed:
        return {**verify_bundle(target, expected), "downloaded": False}
    return {**result, "downloaded": True}

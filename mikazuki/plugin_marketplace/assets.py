"""Managed business-data update channel (F3-3).

The publisher ships ``trainer-assets-<assetsVersion>.zip`` plus a signed
``assets-index.json`` envelope signed with the SAME HMAC keys as the plugin
catalog (see trust.canonical_assets_index_payload). The host applies the
archive into the plugin's data root, inside managed namespaces only
(``knowledge/``, ``templates/``, ``skills/``):

* files tracked by the previously applied manifest are added/updated/deleted
  to match the release;
* a tracked file that was modified locally (sha differs from the record) is
  first copied under ``managed/local-backups/<ts>/`` and then updated, and the
  backup is reported — user work is never silently swallowed;
* files that were never in any manifest are the user's own: they are never
  touched, and a tracked-but-locally-modified file removed from the release
  stays on disk (reported as ``retained_local``);
* the manifest swaps LAST. any failure mid-apply undoes every planned
  mutation from in-memory originals and keeps the previous manifest intact —
  a half-applied managed tree cannot be observed.

Transport stays untrusted: the index must verify before anything is fetched,
the zip must match the index-pinned size+sha256, every member is re-hashed
against the in-zip MANIFEST.json, and only whitelisted path prefixes and
contained relative paths are ever written.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from .catalog import CatalogError
from .paths import MarketplacePaths
from .trust import TrustError, TrustStore

_SAFE_VERSION = re.compile(r"^[0-9A-Za-z._-]{1,64}$")
_HEX64 = re.compile(r"[0-9a-fA-F]{64}")
MAX_INDEX_BYTES = 1 * 1024 * 1024
MAX_ASSETS_TOTAL_BYTES = 64 * 1024 * 1024
MAX_ASSETS_FILES = 2000
# zip member prefix -> data-root-relative namespace root. "skills/" lands in
# the pi user-scope auto-discovery dir (<data>/pi-agent/skills) per F3-0.
NAMESPACE_ROOTS = {
    "knowledge/": "",
    "templates/": "",
    "skills/": "pi-agent",
}
MANIFEST_NAME = "MANIFEST.json"


class AssetsError(CatalogError):
    """Same shape as CatalogError so the marketplace API maps it uniformly."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AssetsUpdater:
    def __init__(
        self,
        paths: MarketplacePaths,
        trust: TrustStore,
        *,
        index_url: str | None = None,
        mirror_base_url: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.paths = paths
        self.trust = trust
        self.index_url = (index_url or "").strip() or None
        if self.index_url:
            self._validate_url(self.index_url, "assets index URL")
        self._mirror = self._validate_mirror(mirror_base_url)
        self.timeout_seconds = timeout_seconds

    # --- URL policy (mirrors the catalog/package channels) -------------------

    @staticmethod
    def _validate_url(url: str, label: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"{label} must be a plain http(s) URL without credentials")
        if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(f"plain-HTTP {label} must be loopback-only")

    @staticmethod
    def _validate_mirror(mirror: str | None) -> str | None:
        if mirror is None or not mirror.strip():
            return None
        mirror = mirror.strip()
        parsed = urlsplit(mirror)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("assets mirror base URL must be a plain http(s) URL without credentials")
        if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("plain-HTTP assets mirrors must be loopback-only")
        return mirror.rstrip("/")

    def _resolve(self, url: str) -> str:
        if self._mirror is None:
            return url
        return f"{self._mirror}{urlsplit(url).path}"

    # --- fetch ---------------------------------------------------------------

    def _fetch(self, url: str, cap: int) -> bytes:
        try:
            request = urllib.request.Request(self._resolve(url), headers={"Accept": "application/json, application/zip"})
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read(cap + 1)
        except (urllib.error.URLError, OSError) as exc:
            raise AssetsError(
                "MARKETPLACE_ASSETS_OFFLINE",
                "The assets channel could not be reached.",
                status_code=503,
            ) from exc
        if len(payload) > cap:
            raise AssetsError(
                "MARKETPLACE_ASSETS_TOO_LARGE",
                "The downloaded assets payload exceeds the size limit.",
                status_code=502,
            )
        return payload

    def _fetch_index(self) -> dict:
        try:
            index = json.loads(self._fetch(self.index_url or "", MAX_INDEX_BYTES).decode("utf-8"))
        except AssetsError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AssetsError("MARKETPLACE_ASSETS_INDEX_INVALID", "The assets index is not valid JSON.", status_code=502) from exc
        if not isinstance(index, dict):
            raise AssetsError("MARKETPLACE_ASSETS_INDEX_INVALID", "The assets index must be a JSON object.", status_code=502)
        for field in ("assetsVersion", "file", "url", "sha256", "size"):
            if field not in index:
                raise AssetsError("MARKETPLACE_ASSETS_INDEX_INVALID", f"The assets index is missing {field}.", status_code=502)
        if not _SAFE_VERSION.fullmatch(str(index["assetsVersion"])):
            raise AssetsError("MARKETPLACE_ASSETS_INDEX_INVALID", "The assets index carries an unsafe assetsVersion.", status_code=502)
        if not isinstance(index["size"], int) or index["size"] <= 0:
            raise AssetsError("MARKETPLACE_ASSETS_INDEX_INVALID", "The assets index size is invalid.", status_code=502)
        if not _HEX64.fullmatch(str(index["sha256"])):
            raise AssetsError("MARKETPLACE_ASSETS_INDEX_INVALID", "The assets index sha256 is invalid.", status_code=502)
        return index

    # --- status (no network) ---------------------------------------------------

    def status(self, plugin_id: str) -> dict:
        manifest_file = self._manifest_file(plugin_id)
        payload: dict = {"configured": self.index_url is not None}
        if manifest_file.is_file():
            try:
                current = json.loads(manifest_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = None
            if isinstance(current, dict):
                payload.update(
                    {
                        "assetsVersion": current.get("assetsVersion"),
                        "fileCount": len(current.get("files") or {}),
                        "appliedAt": current.get("appliedAt"),
                    }
                )
        backups = self.paths.user_data_dir(plugin_id) / "managed" / "local-backups"
        if backups.is_dir():
            payload["backupCount"] = sum(1 for item in backups.iterdir() if item.is_dir())
        return payload

    # --- update --------------------------------------------------------------

    def update(self, plugin_id: str) -> dict:
        if self.index_url is None:
            raise AssetsError(
                "MARKETPLACE_ASSETS_OFFLINE",
                "No assets index URL is configured.",
                status_code=503,
            )
        data_root = self.paths.user_data_dir(plugin_id)
        previous = self._read_manifest(plugin_id)
        index = self._fetch_index()
        try:
            self.trust.verify_assets_index(index)
        except TrustError as exc:
            raise AssetsError(
                "MARKETPLACE_ASSETS_UNTRUSTED",
                "The assets index could not be verified.",
                status_code=503,
            ) from exc
        payload = self._fetch(str(index["url"]), MAX_ASSETS_TOTAL_BYTES)
        if len(payload) != int(index["size"]) or not _sha256_bytes(payload) == str(index["sha256"]).lower():
            raise AssetsError(
                "MARKETPLACE_ASSETS_CHECKSUM_MISMATCH",
                "The assets package checksum does not match the signed index.",
                status_code=502,
            )
        import io

        incoming = self._inspect_zip(io.BytesIO(payload))
        persisted = {rel: {"sha256": meta["sha256"], "size": meta["size"]} for rel, meta in incoming.items()}
        report = self._apply(data_root, previous, incoming)
        manifest = {
            "assetsVersion": index["assetsVersion"],
            "files": persisted,
            "appliedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sourceFile": str(index["file"]),
            "indexSignature": str(index.get("signature") or ""),
        }
        self._write_manifest(plugin_id, manifest)
        report.update({"assetsVersion": index["assetsVersion"], "bytesDownloaded": len(payload)})
        return report

    # --- archive ---------------------------------------------------------------

    def _inspect_zip(self, stream) -> dict[str, dict]:
        try:
            archive = zipfile.ZipFile(stream)
        except zipfile.BadZipFile as exc:
            raise AssetsError("MARKETPLACE_ASSETS_PACKAGE_INVALID", "The assets package is not a valid zip.", status_code=502) from exc
        with archive:
            if MANIFEST_NAME not in archive.namelist():
                raise AssetsError(
                    "MARKETPLACE_ASSETS_PACKAGE_INVALID",
                    f"The assets package has no {MANIFEST_NAME}.",
                    status_code=502,
                )
            try:
                manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AssetsError("MARKETPLACE_ASSETS_PACKAGE_INVALID", f"{MANIFEST_NAME} is not valid JSON.", status_code=502) from exc
            entries = manifest.get("files") if isinstance(manifest, dict) else None
            if not isinstance(entries, list) or len(entries) > MAX_ASSETS_FILES:
                raise AssetsError("MARKETPLACE_ASSETS_PACKAGE_INVALID", f"{MANIFEST_NAME} files list is invalid.", status_code=502)
            incoming: dict[str, dict] = {}
            for item in entries:
                if not isinstance(item, dict):
                    raise AssetsError("MARKETPLACE_ASSETS_PACKAGE_INVALID", f"{MANIFEST_NAME} file entry is invalid.", status_code=502)
                rel = str(item.get("path") or "")
                sha = str(item.get("sha256") or "")
                size = item.get("size")
                if not self._safe_member_path(rel) or not _HEX64.fullmatch(sha) or not isinstance(size, int) or size <= 0:
                    raise AssetsError("MARKETPLACE_ASSETS_PACKAGE_INVALID", f"{MANIFEST_NAME} rejected member path: {rel!r}", status_code=502)
                try:
                    body = archive.read(rel)
                except KeyError as exc:
                    raise AssetsError(
                        "MARKETPLACE_ASSETS_PACKAGE_INVALID",
                        f"Assets package is missing {rel}.",
                        status_code=502,
                    ) from exc
                if len(body) != size or _sha256_bytes(body) != sha.lower():
                    raise AssetsError(
                        "MARKETPLACE_ASSETS_PACKAGE_INVALID",
                        f"Assets package member does not match {MANIFEST_NAME}: {rel}",
                        status_code=502,
                    )
                incoming[rel] = {"sha256": sha.lower(), "size": size, "_body": body}
            return incoming

    @staticmethod
    def _safe_member_path(rel: str) -> bool:
        if not rel or rel.startswith("/") or "\\" in rel or ".." in rel.split("/"):
            return False
        return any(rel.startswith(prefix) for prefix in NAMESPACE_ROOTS)

    def _target(self, data_root: Path, rel: str) -> Path:
        for prefix, root in NAMESPACE_ROOTS.items():
            if rel.startswith(prefix):
                target = (data_root / root / rel).resolve()
                if data_root.resolve() not in target.parents and target != data_root.resolve():
                    from .paths import PathPolicyError

                    raise PathPolicyError(f"assets path escapes the plugin data root: {rel}")
                return target
        raise AssetsError("MARKETPLACE_ASSETS_PACKAGE_INVALID", f"unmapped namespace: {rel}", status_code=502)

    # --- apply with full undo ---------------------------------------------------

    def _apply(self, data_root: Path, previous: dict, incoming: dict) -> dict:
        tracked: dict = dict((previous or {}).get("files") or {})
        report = {"added": [], "updated": [], "backed_up": [], "deleted": [], "retained_local": [], "unchanged": []}
        undo: list[tuple[Path, bytes | None]] = []
        backup_root = data_root / "managed" / "local-backups" / time.strftime("%Y%m%d-%H%M%S")
        try:
            for rel, meta in sorted(incoming.items()):
                target = self._target(data_root, rel)
                disk_sha = _sha256_file(target) if target.is_file() else None
                body = meta["_body"]
                if disk_sha is None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    self._atomic_write(target, body)
                    undo.append((target, None))
                    report["added" if rel not in tracked else "updated"].append(rel)
                elif disk_sha == meta["sha256"]:
                    report["unchanged"].append(rel)
                else:
                    original = target.read_bytes()
                    recorded = tracked.get(rel)
                    if recorded is None or recorded.get("sha256") != disk_sha:
                        # user-modified (or an untracked same-path collision):
                        # back the user's bytes up BEFORE the update lands.
                        backup = backup_root / rel
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(target, backup)
                        report["backed_up"].append(rel)
                    self._atomic_write(target, body)
                    undo.append((target, original))
                    report["updated"].append(rel)
            for rel in sorted(set(tracked) - set(incoming)):
                target = self._target(data_root, rel)
                if not target.is_file():
                    continue
                recorded = tracked.get(rel) or {}
                disk_sha = _sha256_file(target)
                if disk_sha == recorded.get("sha256"):
                    undo.append((target, target.read_bytes()))
                    target.unlink()
                    report["deleted"].append(rel)
                else:
                    report["retained_local"].append(rel)
        except Exception:
            for target, original in reversed(undo):
                try:
                    if original is None:
                        target.unlink(missing_ok=True)
                    else:
                        self._atomic_write(target, original)
                except OSError:
                    pass  # last-resort: the managed manifest (not yet swapped) still describes the old truth
            raise
        for key in report:
            report[key] = sorted(report[key])
        report["updated"] = sorted(set(report["updated"]) - set(report["added"]))
        report["backupPath"] = str(backup_root.relative_to(data_root)) if report["backed_up"] else None
        return report

    # --- manifest ----------------------------------------------------------------

    def _manifest_file(self, plugin_id: str) -> Path:
        return self.paths.user_data_dir(plugin_id) / "managed" / "managed-manifest.json"

    def _read_manifest(self, plugin_id: str) -> dict:
        path = self._manifest_file(plugin_id)
        if not path.is_file():
            return {"assetsVersion": None, "files": {}}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AssetsError(
                "MARKETPLACE_ASSETS_MANIFEST_UNREADABLE",
                "The local managed-assets manifest is unreadable; refusing to mutate the tree.",
                status_code=500,
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("files"), dict):
            raise AssetsError(
                "MARKETPLACE_ASSETS_MANIFEST_UNREADABLE",
                "The local managed-assets manifest has an invalid shape.",
                status_code=500,
            )
        return payload

    def _write_manifest(self, plugin_id: str, manifest: dict) -> None:
        path = self._manifest_file(plugin_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8"))

    @staticmethod
    def _atomic_write(target: Path, body: bytes) -> None:
        temp = target.with_name(target.name + ".tmp")
        temp.write_bytes(body)
        os.replace(temp, target)

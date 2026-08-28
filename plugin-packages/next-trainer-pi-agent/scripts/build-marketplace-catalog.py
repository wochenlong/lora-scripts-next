# /// script
# requires-python = ">=3.11"
# ///
"""Build the dual-platform (win32-x64 + linux-x64) local/test marketplace
catalog + trust root (Goal v9 / Linux 适配).

Reads both platform zips from dist-marketplace/packages/, binds each to its
platform via the entry's `packages` list (flat fields stay the win32-x64
binding for legacy readers), signs everything with the dev HMAC key, and
self-checks every binding with the host's own validators.

NOTE: the `packages` field requires a host with the dual-platform catalog
schema; single-platform hosts parse the entry with extra="forbid" and must
keep using single-platform catalogs.

Run with the project venv:
  .venv-dev\\Scripts\\python.exe plugin-packages\\next-trainer-pi-agent\\scripts\\build-marketplace-catalog.py
"""
from __future__ import annotations

import hashlib
import hmac as hmac_module
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PKG_ROOT.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

VERSION = "0.2.0"
PLUGIN_ID = "next-trainer-pi-agent"
PUBLISHER = "next-trainer-project"
HOST_COMPAT = ">=2.9.2 <4.0.0"
PLATFORMS = ["win32-x64", "linux-x64"]
SIGNING_KEY_ID = "dev-local-signing"
SIGNING_KEY_HEX = "6e6578742d747261696e65722d6c6f63616c2d746573742d7369676e696e672d6b6579"
OUT_DIR = PKG_ROOT / "dist-marketplace"

MAX_PACKAGE_BYTES = 1024 * 1024 * 1024
MAX_UNPACKED_BYTES = 4 * 1024 * 1024 * 1024
MAX_FILES = 300_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hmac_sign(key: bytes, payload: bytes) -> str:
    return hmac_module.new(key, payload, hashlib.sha256).hexdigest()


def _host_version() -> str:
    try:
        return (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def main() -> int:
    from mikazuki.plugin_marketplace.models import MarketplaceCatalog, MarketplaceEntry
    from mikazuki.plugin_marketplace.package import PackageLimits, inspect_package, validate_manifest_entry
    from mikazuki.plugin_marketplace.trust import TrustStore, canonical_catalog_payload, canonical_entry_payload

    zips = {platform: OUT_DIR / "packages" / f"{PLUGIN_ID}-{VERSION}-{platform}.zip" for platform in PLATFORMS}
    for platform, path in zips.items():
        if not path.is_file():
            raise SystemExit(f"missing platform package: {path}")

    sizes = {platform: path.stat().st_size for platform, path in zips.items()}
    shas = {platform: sha256_file(path) for platform, path in zips.items()}
    for platform, size in sizes.items():
        if size > MAX_PACKAGE_BYTES:
            raise SystemExit(f"{platform} package size {size} exceeds limit {MAX_PACKAGE_BYTES}")

    urls = {
        platform: f"https://plugins.next-trainer.local/packages/{PLUGIN_ID}-{VERSION}-{platform}.zip"
        for platform in PLATFORMS
    }
    # Flat fields carry the win32-x64 binding (legacy readers + display).
    primary = "win32-x64"

    key = bytes.fromhex(SIGNING_KEY_HEX)
    entry = MarketplaceEntry(
        id=PLUGIN_ID,
        name="Next Trainer Pi Agent",
        publisher_id=PUBLISHER,
        description=(
            "Verbatim pi-web (v0.8.9) with the pi coding agent (0.84.2, npm) embedded as a "
            "loopback server and opened in the cross-page floating dialog. Ships win32-x64 and "
            "linux-x64 packages (local/test catalog)."
        ),
        icon=None,
        latest_version=VERSION,
        channel="stable",
        host_compatibility=HOST_COMPAT,
        platforms=PLATFORMS,
        package_size=sizes[primary],
        permissions_summary=[],
        license="MIT",
        release_notes_url=None,
        package_url=urls[primary],
        sha256=shas[primary],
        signature="",
        signing_key_id=SIGNING_KEY_ID,
        published_at=datetime.now(timezone.utc).replace(microsecond=0),
        packages=[
            {"platform": platform, "package_url": urls[platform], "package_size": sizes[platform], "sha256": shas[platform]}
            for platform in PLATFORMS
        ],
    )
    entry.signature = _hmac_sign(key, canonical_entry_payload(entry))

    catalog = MarketplaceCatalog(
        schema_version=1,
        publisher_id=PUBLISHER,
        signing_key_id=SIGNING_KEY_ID,
        generated_at=datetime.now(timezone.utc).replace(microsecond=0),
        entries=[entry],
        signature="",
    )
    catalog.signature = _hmac_sign(key, canonical_catalog_payload(catalog))

    (OUT_DIR / "catalog.json").write_text(
        json.dumps(catalog.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "trust.json").write_text(
        json.dumps(
            {
                "keys": {SIGNING_KEY_ID: {"publisherId": PUBLISHER, "keyHex": SIGNING_KEY_HEX}},
                "revokedKeys": [],
                "note": "Development/test trust root only. Production signing is release-governed.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Self-check every platform binding with the host's own validators.
    limits = PackageLimits(
        max_package_bytes=MAX_PACKAGE_BYTES,
        max_unpacked_bytes=MAX_UNPACKED_BYTES,
        max_files=MAX_FILES,
    )
    trust = TrustStore({SIGNING_KEY_ID: (PUBLISHER, key)})
    for platform in PLATFORMS:
        manifest, _members = inspect_package(zips[platform], limits)
        validate_manifest_entry(manifest, entry, platform=platform)
        url, size, sha = entry.resolve_platform_package(platform)
        trust.verify(entry, zips[platform], package_size=size, sha256=sha)
        trust.verify_compatibility(entry, host_version=_host_version(), platform=platform)
        assert url == urls[platform]
        print(f"[self-check] {platform}: inspect + manifest + trust verify + compatibility: PASS")
    trust.verify_catalog(catalog)
    print("[self-check] catalog signature: PASS")

    print(json.dumps(
        {
            "catalog": str(OUT_DIR / "catalog.json"),
            "trust": str(OUT_DIR / "trust.json"),
            "packages": {
                platform: {"zip": str(zips[platform]), "bytes": sizes[platform], "sha256": shas[platform]}
                for platform in PLATFORMS
            },
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

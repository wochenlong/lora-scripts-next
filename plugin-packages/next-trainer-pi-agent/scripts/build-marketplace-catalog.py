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

import argparse
import hashlib
import hmac as hmac_module
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

PKG_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PKG_ROOT.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

VERSION = "0.3.2"
PLUGIN_ID = "next-trainer-pi-agent"
PUBLISHER = "next-trainer-project"
HOST_COMPAT = ">=2.9.2 <4.0.0"
PLATFORMS = ["win32-x64", "linux-x64"]
SIGNING_KEY_ID = "dev-local-signing"
SIGNING_KEY_HEX = "6e6578742d747261696e65722d6c6f63616c2d746573742d7369676e696e672d6b6579"
IN_DIR = PKG_ROOT / "dist-marketplace"
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--remote-base",
        default=None,
        help=(
            "Base URL for real distribution (e.g. "
            "https://github.com/<owner>/<repo>/releases/download/v0.3.2). "
            "When set, catalog URLs become <base>/<file> instead of the "
            "dev-local placeholder; requires a public HTTPS host."
        ),
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Write catalog.json/trust.json here instead of dist-marketplace/ (zip inputs are still read from dist-marketplace/packages/).",
    )
    parser.add_argument(
        "--signing-key-id",
        default=None,
        help="Release signing key id (default: dev-local-signing). Also MIKAZUKI_RELEASE_SIGNING_KEY_ID.",
    )
    parser.add_argument(
        "--signing-key-hex",
        default=None,
        help=(
            "Release signing HMAC key, 64+ hex chars (generate with "
            "python -c \"import secrets; print(secrets.token_hex(32))\"). "
            "Keep it OUT of the repository; the matching trust.json ships "
            "inside the release package only. Also MIKAZUKI_RELEASE_SIGNING_KEY_HEX."
        ),
    )
    args = parser.parse_args(argv)
    remote_base = args.remote_base.rstrip("/") if args.remote_base else None
    if remote_base is not None:
        parsed = urlsplit(remote_base)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise SystemExit("--remote-base must be a plain HTTPS base URL")
    global OUT_DIR, SIGNING_KEY_ID, SIGNING_KEY_HEX
    if args.out_dir:
        OUT_DIR = Path(args.out_dir).resolve()
        OUT_DIR.mkdir(parents=True, exist_ok=True)

    signing_key_id = args.signing_key_id or os.environ.get("MIKAZUKI_RELEASE_SIGNING_KEY_ID", "").strip()
    signing_key_hex = (
        args.signing_key_hex or os.environ.get("MIKAZUKI_RELEASE_SIGNING_KEY_HEX", "").strip()
    ).casefold()
    if (signing_key_id and not signing_key_hex) or (signing_key_hex and not signing_key_id):
        raise SystemExit("release signing requires BOTH --signing-key-id and --signing-key-hex (or the MIKAZUKI_RELEASE_SIGNING_* env pair)")
    if signing_key_id and signing_key_hex:
        if not re.fullmatch(r"[0-9a-f]{32,}", signing_key_hex):
            raise SystemExit("--signing-key-hex must be 64+ hex characters (>=32 bytes)")
        SIGNING_KEY_ID, SIGNING_KEY_HEX = signing_key_id, signing_key_hex
        print(f"[signing] release key: {SIGNING_KEY_ID}")
    elif remote_base:
        print(
            "[signing] WARNING: --remote-base catalog signed with the DEV key. "
            "Use --signing-key-id/--signing-key-hex for public distribution.",
            file=sys.stderr,
        )

    from mikazuki.plugin_marketplace.models import MarketplaceCatalog, MarketplaceEntry
    from mikazuki.plugin_marketplace.package import PackageLimits, inspect_package, validate_manifest_entry
    from mikazuki.plugin_marketplace.trust import TrustStore, canonical_catalog_payload, canonical_entry_payload

    zips = {platform: IN_DIR / "packages" / f"{PLUGIN_ID}-{VERSION}-{platform}.zip" for platform in PLATFORMS}
    for platform, path in zips.items():
        if not path.is_file():
            raise SystemExit(f"missing platform package: {path}")

    sizes = {platform: path.stat().st_size for platform, path in zips.items()}
    shas = {platform: sha256_file(path) for platform, path in zips.items()}
    for platform, size in sizes.items():
        if size > MAX_PACKAGE_BYTES:
            raise SystemExit(f"{platform} package size {size} exceeds limit {MAX_PACKAGE_BYTES}")

    urls = {
        platform: (
            f"{remote_base}/{PLUGIN_ID}-{VERSION}-{platform}.zip"
            if remote_base
            else f"https://plugins.next-trainer.local/packages/{PLUGIN_ID}-{VERSION}-{platform}.zip"
        )
        for platform in PLATFORMS
    }
    # Flat fields carry the win32-x64 binding (legacy readers + display).
    primary = "win32-x64"

    key = bytes.fromhex(SIGNING_KEY_HEX)
    entry = MarketplaceEntry(
        id=PLUGIN_ID,
        name="Next Trainer Agent",
        publisher_id=PUBLISHER,
        description=(
            "Next Trainer Agent embedded as a loopback server and opened in the cross-page "
            "floating dialog. Ships win32-x64 and linux-x64 packages (local/test catalog)."
        ),
        icon=None,
        latest_version=VERSION,
        channel="stable",
        host_compatibility=HOST_COMPAT,
        platforms=PLATFORMS,
        package_size=sizes[primary],
        permissions_summary=[
            "training-config",
            "dataset-review",
            "caption-commit",
            "metrics-read",
            "artifacts-read",
            "external-civitai-read",
        ],
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
                "note": (
                    f"Release trust root (key {SIGNING_KEY_ID}). The signing key is held by the release operator and never committed to the repository."
                    if SIGNING_KEY_ID != "dev-local-signing"
                    else (
                        "Release trust root (dev HMAC key) for remote-distribution catalogs."
                        if remote_base
                        else "Development/test trust root only. Production signing is release-governed."
                    )
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if remote_base:
        print(f"[catalog] remote base URL: {remote_base}")

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
    raise SystemExit(main(sys.argv[1:]))

"""Generate the local/test trusted marketplace catalog for development.

Produces, under dev-catalog/:
  next-trainer-pi-agent-<version>.zip   signed Agent package (build output, gitignored)
  catalog.json                          signed catalog (committed dev asset)
  trust.json                            dev trust root (committed; TEST key only)
  acquire-map.json                      package_url -> local file map (committed)

The signing key is a deterministic development key for the local/test loop.
Production signing material is release-governed and never used here.

Usage:
  .venv-dev\\Scripts\\python.exe plugin-packages/next-trainer-pi-agent/scripts/generate-dev-catalog.py
"""
import hashlib
import hmac
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT = PACKAGE_ROOT.parent.parent
sys.path.insert(0, str(PROJECT))

from mikazuki.plugin_marketplace.models import MarketplaceCatalog, MarketplaceEntry  # noqa: E402
from mikazuki.plugin_marketplace.trust import (  # noqa: E402
    canonical_catalog_payload,
    canonical_entry_payload,
)

PLUGIN_ID = "next-trainer-pi-agent"
OUT = PACKAGE_ROOT / "dev-catalog"
SIGNING_KEY_ID = "dev-local-signing"
SIGNING_KEY = b"next-trainer-local-test-signing-key"


def build_package(version: str) -> Path:
    manifest = json.loads((PACKAGE_ROOT / "plugin.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    package = OUT / f"{PLUGIN_ID}-{version}.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
        archive.writestr(
            "bin/next-trainer-pi-agent.exe",
            (PACKAGE_ROOT / "dist" / "bin" / "next-trainer-pi-agent.exe").read_bytes(),
        )
        for name in ("index.html", "index.js", "index.css", "settings.html"):
            archive.write(PACKAGE_ROOT / "dist" / "ui" / name, f"ui/{name}")
        archive.write(PACKAGE_ROOT / "sbom.cdx.json", "sbom.cdx.json")
        archive.write(PACKAGE_ROOT / "LICENSES" / "MIT.txt", "LICENSE")
        archive.write(PACKAGE_ROOT / "LICENSES" / "MIT.txt", "LICENSES/MIT.txt")
    return package


def main() -> None:
    manifest = json.loads((PACKAGE_ROOT / "plugin.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    OUT.mkdir(parents=True, exist_ok=True)
    package = build_package(version)

    package_url = f"https://dev-catalog.local/{PLUGIN_ID}-{version}.zip"
    value = {
        "id": PLUGIN_ID,
        "name": "Next Trainer Pi Agent",
        "publisher_id": manifest["publisher"],
        "description": "Optional Pi Agent training assistant (local/test catalog).",
        "latest_version": version,
        "channel": "stable",
        "host_compatibility": manifest["hostCompatibility"],
        "platforms": manifest["platforms"],
        "package_size": package.stat().st_size,
        "permissions_summary": manifest["permissions"],
        "license": "MIT",
        "package_url": package_url,
        "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "signing_key_id": SIGNING_KEY_ID,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "signature": "",
    }
    entry = MarketplaceEntry.model_validate(value)
    value["signature"] = hmac.new(SIGNING_KEY, canonical_entry_payload(entry), hashlib.sha256).hexdigest()
    entry = MarketplaceEntry.model_validate(value)

    catalog_value = {
        "schemaVersion": 1,
        "publisherId": manifest["publisher"],
        "signingKeyId": SIGNING_KEY_ID,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "entries": [entry.model_dump(mode="json", by_alias=True)],
        "signature": "",
    }
    catalog = MarketplaceCatalog.model_validate(catalog_value)
    catalog_value["signature"] = hmac.new(
        SIGNING_KEY, canonical_catalog_payload(catalog), hashlib.sha256
    ).hexdigest()
    catalog = MarketplaceCatalog.model_validate(catalog_value)

    (OUT / "catalog.json").write_text(json.dumps(catalog_value, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "trust.json").write_text(
        json.dumps(
            {
                "keys": {SIGNING_KEY_ID: {"publisherId": manifest["publisher"], "keyHex": SIGNING_KEY.hex()}},
                "revokedKeys": [],
                "note": "Development/test trust root only. Production signing is release-governed.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / "acquire-map.json").write_text(
        json.dumps({package_url: str(package)}, indent=2), encoding="utf-8"
    )
    print("package:", package, package.stat().st_size, "bytes")
    print("sha256:", hashlib.sha256(package.read_bytes()).hexdigest())
    print("dev-catalog assets written under", OUT)
    for label, path in (
        ("MIKAZUKI_PLUGIN_CATALOG_PATH", OUT / "catalog.json"),
        ("MIKAZUKI_PLUGIN_CATALOG_TRUST", OUT / "trust.json"),
        ("MIKAZUKI_PLUGIN_PACKAGE_SOURCES", OUT / "acquire-map.json"),
    ):
        print("run app with:", label + "= " + str(path))
    print("GEN-DEV-CATALOG=OK")


if __name__ == "__main__":
    main()

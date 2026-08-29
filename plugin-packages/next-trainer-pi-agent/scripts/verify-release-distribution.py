# /// script
# requires-python = ">=3.11"
# ///
"""Release-distribution dry-run for the marketplace (Stage 2 / B1).

Builds a remote-base (release form) catalog with build-marketplace-catalog.py,
serves the platform zips from a temporary local HTTP file server, and acquires
the win32 package through the real acquisition stack:

    LocalFirstPackageAcquirer(empty local map) -> HttpPackageAcquirer(mirror)

The mirror rewrites the catalog's public HTTPS URL onto the loopback file
server, which is exactly how a future GitHub-release asset URL will be served
for real (integrity still comes from the catalog-pinned size + sha256).

Run from the project root with the project venv:
  .venv-dev\\Scripts\\python.exe plugin-packages\\next-trainer-pi-agent\\scripts\\verify-release-distribution.py
"""

from __future__ import annotations

import hashlib
import http.server
import json
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PKG_ROOT.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

PLUGIN_ID = "next-trainer-pi-agent"
# Version is read from the plugin's own plugin.json so this dry-run never drifts
# behind a release bump (the release-form catalog URL follows the same value).
VERSION = json.loads((PKG_ROOT / "plugin.json").read_text(encoding="utf-8"))["version"]
REMOTE_BASE = f"https://plugins.next-trainer.example.com/releases/download/v{VERSION}"
REL_PATH = f"/releases/download/v{VERSION}"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nt-release-dryrun-") as td:
        td_path = Path(td)
        out_dir = td_path / "release-catalog"
        serve_dir = td_path / "http-root" / REL_PATH.strip("/")
        serve_dir.mkdir(parents=True)

        # 1. Build the remote-base (release form) catalog into a scratch dir.
        result = subprocess.run(
            [
                sys.executable,
                str(PKG_ROOT / "scripts" / "build-marketplace-catalog.py"),
                "--remote-base", REMOTE_BASE,
                "--out-dir", str(out_dir),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr)
            raise SystemExit("catalog build failed")
        catalog = json.loads((out_dir / "catalog.json").read_text(encoding="utf-8"))
        entry = catalog["entries"][0]
        win_url = next(p["package_url"] for p in entry["packages"] if p["platform"] == "win32-x64")
        print("[dry-run] win32 catalog URL:", win_url)
        assert win_url == f"{REMOTE_BASE}/{PLUGIN_ID}-{VERSION}-win32-x64.zip"

        # 2. Stage the win32 zip under the release path layout for the file server.
        source_zip = PKG_ROOT / "dist-marketplace" / "packages" / f"{PLUGIN_ID}-{VERSION}-win32-x64.zip"
        shutil.copy2(source_zip, serve_dir / source_zip.name)

        # 3. Local HTTP file server on a free loopback port.
        http_root = serve_dir.parents[2]

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(http_root), **kwargs)

            def log_message(self, *args) -> None:
                pass

        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), QuietHandler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"[dry-run] file server on http://127.0.0.1:{port}{REL_PATH}/")

        # 4. Acquire through the real acquisition stack (mirror = local server).
        from mikazuki.plugin_marketplace.api import load_trust_root
        from mikazuki.plugin_marketplace.catalog import (
            FileCatalogSource,
            HttpPackageAcquirer,
            LocalFirstPackageAcquirer,
            LocalPackageAcquirer,
            MarketplaceCatalogService,
        )
        from mikazuki.plugin_marketplace.paths import MarketplacePaths

        paths = MarketplacePaths(td_path / "runtime")
        service = MarketplaceCatalogService(
            paths=paths,
            trust=load_trust_root(out_dir / "trust.json"),
            source=FileCatalogSource(out_dir / "catalog.json"),
            acquirer=LocalFirstPackageAcquirer(
                LocalPackageAcquirer({}),  # no local map: release path
                HttpPackageAcquirer(f"http://127.0.0.1:{port}"),
            ),
        )
        service.refresh()
        resolved = service.entry(PLUGIN_ID)
        progress: list[tuple[int, int]] = []
        destination = service.acquire(resolved, "win32-x64", on_progress=lambda c, t: progress.append((c, t)))

        payload = destination.read_bytes()
        expect_sha = hashlib.sha256(payload).hexdigest()
        url, size, sha = resolved.resolve_platform_package("win32-x64")
        server.shutdown()

        assert size == len(payload), (size, len(payload))
        assert sha == expect_sha
        assert progress[0][0] == 0 and progress[-1] == (size, size)
        print(f"[dry-run] downloaded {size} bytes via mirror, sha256 verified: {sha[:16]}...")
        print("[dry-run] RELEASE-DISTRIBUTION PATH: PASS")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

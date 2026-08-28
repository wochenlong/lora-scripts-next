# /// script
# requires-python = ">=3.11"
# ///
"""Build the verbatim pi-web plugin package (Goal v9 / CR-011, S4).

Stages the final package layout, prunes node_modules to runtime deps, writes
plugin.json, zips the package, and emits the local/test catalog + trust root
with HMAC test signatures. Then self-checks the result against the host's
own package/trust validators.

Run with the project venv:
  .venv-dev\\Scripts\\python.exe plugin-packages\\next-trainer-pi-agent\\scripts\\build-pi-web-package.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PKG_ROOT.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

VERSION = "0.3.2"
PLUGIN_ID = "next-trainer-pi-agent"
PUBLISHER = "next-trainer-project"
HOST_COMPAT = ">=2.9.2 <4.0.0"
PLATFORMS = ["win32-x64"]
SIGNING_KEY_ID = "dev-local-signing"
SIGNING_KEY_HEX = "6e6578742d747261696e65722d6c6f63616c2d746573742d7369676e696e672d6b6579"
PACKAGE_URL = f"https://plugins.next-trainer.local/packages/{PLUGIN_ID}-{VERSION}-win32-x64.zip"

# Measured S4 values (first full build): tune to at least the measured maxima.
MAX_PACKAGE_BYTES = 1024 * 1024 * 1024  # 1 GiB zip
MAX_UNPACKED_BYTES = 4 * 1024 * 1024 * 1024  # 4 GiB unpacked
MAX_FILES = 300_000

NODE_RUNTIME = Path(r"E:\OpenSourceTeamWork\.dev-runtimes\node-v22.19.0")
NPM_CLI = NODE_RUNTIME / "node_modules" / "npm" / "bin" / "npm-cli.js"

STAGE = PKG_ROOT / "dist-marketplace" / "stage" / VERSION
OUT_DIR = PKG_ROOT / "dist-marketplace"
OUT_ZIP = OUT_DIR / "packages" / f"{PLUGIN_ID}-{VERSION}-win32-x64.zip"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raw_prefix(base: Path) -> str:
    """\\?\\ prefixed absolute path; bypasses the 260-char MAX_PATH limit."""
    return "\\\\?\\" + str(base).replace("/", "\\")


def remove_tree(base: Path) -> None:
    """MAX_PATH-safe recursive delete."""
    if not base.exists() and not base.is_symlink():
        return
    raw_root = raw_prefix(base)
    stack = [raw_root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            try:
                os.rmdir(current)
            except OSError:
                pass
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                else:
                    try:
                        os.unlink(entry.path)
                    except PermissionError:
                        os.chmod(entry.path, 0o700)
                        os.unlink(entry.path)
            except OSError:
                continue
        try:
            os.rmdir(current)
        except OSError:
            pass


def collect_files(base: Path) -> list[tuple[str, str]]:
    """Recursively collect (relpath_posix, raw_abs_path), MAX_PATH-safe."""
    raw_root = raw_prefix(base)
    collected: list[tuple[str, str]] = []

    def walk(raw_dir: str, rel: str) -> None:
        try:
            entries = list(os.scandir(raw_dir))
        except (FileNotFoundError, PermissionError):
            return
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    walk(entry.path, f"{rel}/{entry.name}" if rel else entry.name)
                elif entry.is_file(follow_symlinks=False):
                    child_rel = f"{rel}/{entry.name}" if rel else entry.name
                    collected.append((child_rel, entry.path))
                # links are skipped: the package format forbids them
            except OSError:
                continue

    walk(raw_root, "")
    return collected


def strip_dist_types(node_modules: Path) -> int:
    """Remove dist-types trees (TS type declarations; not needed at runtime
    and the deep layouts exceed MAX_PATH on Windows builds)."""
    removed = 0
    raw_root = raw_prefix(node_modules)
    stack = [raw_root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name == "dist-types":
                        shutil.rmtree(entry.path, ignore_errors=True)
                        removed += 1
                    else:
                        stack.append(entry.path)
            except OSError:
                continue
    return removed


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        remove_tree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["robocopy", str(src), str(dst), "/E", "/MT:16", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"],
        capture_output=True,
        text=True,
    )
    if result.returncode > 7:
        raise RuntimeError(f"robocopy failed ({result.returncode}): {result.stderr}")


def main() -> int:
    # The bundled Node runtime (85 MB) is a build-time input provisioned from
    # the shared dev-runtimes checkout; it is not committed to the repository.
    bundled_node = PKG_ROOT / "runtime" / "node" / "node.exe"
    if not bundled_node.is_file():
        source_node = NODE_RUNTIME / "node.exe"
        if not source_node.is_file():
            raise SystemExit(f"missing build input: {source_node} (provision Node 22.19.0 into .dev-runtimes first)")
        bundled_node.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_node, bundled_node)
        print(f"[stage] provisioned bundled runtime from {source_node}", flush=True)

    for required in (
        PKG_ROOT / "bin" / "next-trainer-pi-agent.exe",
        bundled_node,
        PKG_ROOT / "pi-web" / "bin" / "pi-web.js",
        PKG_ROOT / "pi-web" / ".next" / "BUILD_ID",
        PKG_ROOT / "packaging" / "ui-fallback" / "index.html",
    ):
        if not required.is_file():
            raise SystemExit(f"missing build input: {required}")

    # 1. Stage layout.
    if STAGE.exists():
        remove_tree(STAGE)
    (STAGE / "bin").mkdir(parents=True)
    shutil.copy2(PKG_ROOT / "bin" / "next-trainer-pi-agent.exe", STAGE / "bin" / "next-trainer-pi-agent.exe")
    (STAGE / "runtime" / "node").mkdir(parents=True)
    shutil.copy2(PKG_ROOT / "runtime" / "node" / "node.exe", STAGE / "runtime" / "node" / "node.exe")
    (STAGE / "ui").mkdir(parents=True)
    shutil.copy2(PKG_ROOT / "packaging" / "ui-fallback" / "index.html", STAGE / "ui" / "index.html")

    print("[stage] pi-web (full tree incl. .next and dev node_modules) ...", flush=True)
    copy_tree(PKG_ROOT / "pi-web", STAGE / "pi-web")

    # Drop dev-server leftovers from .next (the dev build tree + the Turbopack
    # filesystem cache) so the production package stays lean. pi-web.js only
    # serves .next/server + .next/static + BUILD_ID; `next build` (Turbopack)
    # reuses .next/cache and does not clear a prior `next dev`'s .next/dev.
    for _dev_leftover in ("dev", "cache"):
        _leftover = STAGE / "pi-web" / ".next" / _dev_leftover
        if _leftover.exists():
            remove_tree(_leftover)
            print(f"[stage] removed .next/{_dev_leftover} (dev leftover)", flush=True)

    print("[stage] npm prune --omit=dev (runtime-only node_modules) ...", flush=True)
    result = subprocess.run(
        [str(NODE_RUNTIME / "node.exe"), str(NPM_CLI), "prune", "--omit=dev", "--no-audit", "--no-fund"],
        cwd=STAGE / "pi-web",
        capture_output=True,
        text=True,
        env={"SystemRoot": r"C:\Windows", "WINDIR": r"C:\Windows", "PATH": r"C:\Windows\System32;C:\Windows"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"npm prune failed: {result.stdout[-2000:]} {result.stderr[-2000:]}")
    # npm prune rewrites the lockfile; restore the verbatim upstream copy so
    # every source-tracked file in the package is byte-identical to HEAD.
    shutil.copy2(PKG_ROOT / "pi-web" / "package-lock.json", STAGE / "pi-web" / "package-lock.json")

    print("[stage] strip dist-types (type declarations, runtime-unneeded) ...", flush=True)
    stripped = strip_dist_types(STAGE / "pi-web" / "node_modules")
    print(f"[stage] removed {stripped} dist-types directories", flush=True)

    # Stage the Next Trainer pi package (extensions + skills + manifest) and the
    # knowledge/template seeds. Only the runtime assets are shipped — the test/
    # directory inside pi-package is a dev artifact and is deliberately excluded.
    print("[stage] pi-package (extensions + skills + package.json) + seeds ...", flush=True)
    (STAGE / "pi-package").mkdir(parents=True, exist_ok=True)
    shutil.copy2(PKG_ROOT / "pi-package" / "package.json", STAGE / "pi-package" / "package.json")
    copy_tree(PKG_ROOT / "pi-package" / "extensions", STAGE / "pi-package" / "extensions")
    copy_tree(PKG_ROOT / "pi-package" / "skills", STAGE / "pi-package" / "skills")
    copy_tree(PKG_ROOT / "seeds", STAGE / "seeds")

    # 2. License inventory + notice.
    (STAGE / "LICENSES").mkdir()
    (STAGE / "LICENSES" / "pi-web-MIT.txt").write_text(
        (PKG_ROOT / "pi-web" / "LICENSE").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (STAGE / "LICENSES" / "pi-agent-MIT.txt").write_text(
        "MIT License\n\n"
        "Copyright (c) 2026 earendil-works (pi packages @earendil-works/pi-* @0.84.2,\n"
        "repository https://github.com/earendil-works/pi; MIT declared in each package.json)\n\n"
        "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
        "of this software and associated documentation files (the \"Software\"), to deal\n"
        "in the Software without restriction, including without limitation the rights\n"
        "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
        "copies of the Software, and to permit persons to whom the Software is\n"
        "furnished to do so, subject to the following conditions:\n\n"
        "The above copyright notice and this permission notice shall be included in all\n"
        "copies or substantial portions of the Software.\n\n"
        "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n"
        "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
        "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
        "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
        "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n"
        "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\n"
        "SOFTWARE.\n",
        encoding="utf-8",
    )
    (STAGE / "NOTICE.md").write_text(
        "# Next Trainer Agent — third-party components\n\n"
        "This plugin embeds unmodified upstream projects (Goal v9 / CR-011):\n\n"
        "- **pi-web v0.8.9** — `github.com/agegr/pi-web` @ `2a6e53710f6409e0cceb3de839a62f8cdf3ca3ca`, "
        "MIT, Copyright (c) 2026 agegr. See `LICENSES/pi-web-MIT.txt` and `pi-web/LICENSE`.\n"
        "- **pi coding agent packages 0.84.2** — `github.com/earendil-works/pi`, npm packages "
        "`@earendil-works/pi-agent-core`, `pi-ai`, `pi-coding-agent`, `pi-tui` (plus transitive `pi-telemetry`), "
        "MIT declared per package. See `LICENSES/pi-agent-MIT.txt`.\n"
        "- **Node.js 22.19.0 runtime** — `node.exe` under `runtime/node/`, Node.js project license.\n"
        "- **Next.js 16.3.1 / React 19.2.4** and other runtime dependencies inside `pi-web/node_modules`, "
        "each under its own upstream license recorded by the npm registry.\n\n"
        "The launcher (`bin/next-trainer-pi-agent.exe`) is Next Trainer packaging glue: it only implements the "
        "host runtime contract (READY/health) and supervises the unmodified pi-web server.\n",
        encoding="utf-8",
    )

    # 3. plugin.json (package sha/signature fields are build markers; the
    #    binding verification happens at the catalog entry level).
    manifest = {
        "id": PLUGIN_ID,
        "publisher": PUBLISHER,
        "version": VERSION,
        "protocolVersion": "1",
        "hostCompatibility": HOST_COMPAT,
        "platforms": PLATFORMS,
        "runtime": {
            "kind": "executable",
            "entrypoint": "bin/next-trainer-pi-agent.exe",
            "buildNode": "22.19.0",
            "embeddedRuntime": "bun-1.4.0-launcher+node-22.19.0-runtime",
        },
        "ui": {
            "entrypoint": "ui/index.html",
            "extensionApi": "1",
            "placements": ["floating-panel"],
        },
        "bridge": {"requests": [], "streams": []},
        # custom-tools + skills: the plugin registers host agent-tools (via the
        # host gateway) and ships pi skills; server-ui: the floating-panel pi-web.
        "capabilities": ["server-ui", "custom-tools", "skills"],
        # Least-privilege set the host grants on enable; these back the 16
        # agent-tools (training-config, dataset-review, caption-commit, metrics,
        # artifacts/knowledge, external-civitai). The tagger reuses caption-commit.
        "permissions": [
            "training-config",
            "dataset-review",
            "caption-commit",
            "metrics-read",
            "artifacts-read",
            "external-civitai-read",
        ],
        "package": {
            "sha256": "BUILD_TIME_VALUE",
            "signature": "TEST_OR_RELEASE_VALUE",
            "sbom": "sbom.cdx.json",
        },
        "installHooks": [],
    }
    (STAGE / "plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 4. SBOM (CycloneDX, minimal metadata + embedded components).
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": PLUGIN_ID,
                "version": VERSION,
            }
        },
        "components": [
            {
                "type": "application",
                "name": "@agegr/pi-web",
                "version": "0.8.9",
                "purl": "pkg:npm/%40agegr/pi-web@0.8.9",
                "licenses": [{"license": {"id": "MIT"}}],
                "description": "Verbatim upstream source + production build; see LICENSES/pi-web-MIT.txt",
            },
            *[
                {
                    "type": "library",
                    "name": name,
                    "version": "0.84.2",
                    "purl": f"pkg:npm/%40earendil-works/{name}@0.84.2",
                    "licenses": [{"license": {"id": "MIT"}}],
                }
                for name in ("pi-agent-core", "pi-ai", "pi-coding-agent", "pi-tui")
            ],
            {"type": "library", "name": "next", "version": "16.3.1", "purl": "pkg:npm/next@16.3.1"},
            {"type": "library", "name": "react", "version": "19.2.4", "purl": "pkg:npm/react@19.2.4"},
            {"type": "library", "name": "node", "version": "22.19.0", "purl": "pkg:github/nodejs/node@v22.19.0"},
        ],
    }
    (STAGE / "sbom.cdx.json").write_text(
        json.dumps(sbom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 5. Measure + zip (MAX_PATH-safe walk; sorted for deterministic output).
    files = sorted(collect_files(STAGE), key=lambda item: item[0])
    file_count = len(files)
    unpacked_bytes = 0
    for _rel, raw in files:
        unpacked_bytes += Path(raw).stat().st_size
    print(f"[measure] files={file_count} unpacked={unpacked_bytes} bytes", flush=True)
    if file_count > MAX_FILES:
        raise SystemExit(f"file count {file_count} exceeds limit {MAX_FILES}")
    if unpacked_bytes > MAX_UNPACKED_BYTES:
        raise SystemExit(f"unpacked size {unpacked_bytes} exceeds limit {MAX_UNPACKED_BYTES}")

    OUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if OUT_ZIP.exists():
        OUT_ZIP.unlink()
    with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for rel, raw in files:
            archive.write(raw, rel)
    package_bytes = OUT_ZIP.stat().st_size
    package_sha = sha256_file(OUT_ZIP)
    if package_bytes > MAX_PACKAGE_BYTES:
        raise SystemExit(f"package size {package_bytes} exceeds limit {MAX_PACKAGE_BYTES}")
    print(f"[zip] {OUT_ZIP.name} bytes={package_bytes} sha256={package_sha}", flush=True)
    # --zip-only: rebuild the platform zip without touching catalog/trust
    # (the dual-platform catalog is emitted by build-marketplace-catalog.py).
    if "--zip-only" in sys.argv:
        print(json.dumps({"zip": str(OUT_ZIP), "bytes": package_bytes, "sha256": package_sha, "files": file_count, "unpacked_bytes": unpacked_bytes}, indent=2))
        return 0

    # 6. Catalog + trust (HMAC test signatures, host modules for canonical form).
    from mikazuki.plugin_marketplace.models import MarketplaceCatalog, MarketplaceEntry
    from mikazuki.plugin_marketplace.package import PackageLimits, inspect_package, validate_manifest_entry
    from mikazuki.plugin_marketplace.trust import TrustStore, canonical_catalog_payload, canonical_entry_payload

    entry = MarketplaceEntry(
        id=PLUGIN_ID,
        name="Next Trainer Agent",
        publisher_id=PUBLISHER,
        description=(
            "Next Trainer Agent embedded as a loopback server and opened in the cross-page "
            "floating dialog (local/test catalog)."
        ),
        icon=None,
        latest_version=VERSION,
        channel="stable",
        host_compatibility=HOST_COMPAT,
        platforms=PLATFORMS,
        package_size=package_bytes,
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
        package_url=PACKAGE_URL,
        sha256=package_sha,
        signature="",
        signing_key_id=SIGNING_KEY_ID,
        published_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    key = bytes.fromhex(SIGNING_KEY_HEX)
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

    # 7. Self-check with the host's own validators.
    limits = PackageLimits(
        max_package_bytes=MAX_PACKAGE_BYTES,
        max_unpacked_bytes=MAX_UNPACKED_BYTES,
        max_files=MAX_FILES,
    )
    manifest_obj, members = inspect_package(OUT_ZIP, limits)
    validate_manifest_entry(manifest_obj, entry)
    trust = TrustStore({SIGNING_KEY_ID: (PUBLISHER, key)})
    trust.verify(entry, OUT_ZIP)
    trust.verify_catalog(catalog)
    trust.verify_compatibility(entry, host_version=_host_version(), platform="win32-x64")
    print("[self-check] inspect_package + manifest/cross-check + trust verify: PASS")

    print(json.dumps(
        {
            "zip": str(OUT_ZIP),
            "bytes": package_bytes,
            "sha256": package_sha,
            "files": file_count,
            "unpacked_bytes": unpacked_bytes,
            "limits": {"max_package_bytes": MAX_PACKAGE_BYTES, "max_unpacked_bytes": MAX_UNPACKED_BYTES, "max_files": MAX_FILES},
            "catalog": str(OUT_DIR / "catalog.json"),
            "trust": str(OUT_DIR / "trust.json"),
        },
        indent=2,
    ))
    return 0


def _hmac_sign(key: bytes, payload: bytes) -> str:
    import hmac as _hmac

    return _hmac.new(key, payload, hashlib.sha256).hexdigest()


def _host_version() -> str:
    version_file = PROJECT_ROOT / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# Dual-platform pipeline (CR-012): assemble the linux-x64 plugin package zip
# inside WSL (avoids shipping the ~1.3 GB extracted tree back over 9p).
#
# Usage:  bash wsl-stage-linux-package.sh
# Inputs: /tmp/nt-pi-linux (from wsl-build-pi-web.sh)
#         <package root>/bin/next-trainer-pi-agent (cross-compiled bun-linux-x64 ELF)
#         <package root>/plugin.json (version of record — keeps the zip name,
#         embedded plugin.json and SBOM in lockstep with the working tree)
# Output: <package root>/dist-marketplace/packages/next-trainer-pi-agent-<version>-linux-x64.zip
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['version'])" "$PKG_ROOT/plugin.json")"

W=/tmp/nt-pi-linux
STAGE=$W/stage
if [ ! -x "$W/node-v22.19.0-linux-x64/bin/node" ] || [ ! -d "$W/src/pi-web/.next" ]; then
  echo "missing WSL build output; run scripts/wsl/wsl-build-pi-web.sh first" >&2
  exit 1
fi
if [ ! -f "$PKG_ROOT/bin/next-trainer-pi-agent" ]; then
  echo "missing cross-compiled launcher: $PKG_ROOT/bin/next-trainer-pi-agent" >&2
  exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE/bin" "$STAGE/runtime/node" "$STAGE/ui" "$STAGE/LICENSES"

cp "$PKG_ROOT/bin/next-trainer-pi-agent" "$STAGE/bin/next-trainer-pi-agent"
chmod 755 "$STAGE/bin/next-trainer-pi-agent"
cp "$W/node-v22.19.0-linux-x64/bin/node" "$STAGE/runtime/node/node"
chmod 755 "$STAGE/runtime/node/node"
cp "$PKG_ROOT/packaging/ui-fallback/index.html" "$STAGE/ui/index.html"
cp "$W/src/pi-web/LICENSE" "$STAGE/LICENSES/pi-web-MIT.txt"

cat > "$STAGE/LICENSES/pi-agent-MIT.txt" <<'EOF'
MIT License

Copyright (c) 2026 earendil-works (pi packages @earendil-works/pi-* @0.84.2,
repository https://github.com/earendil-works/pi; MIT declared in each package.json)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF

cat > "$STAGE/NOTICE.md" <<'EOF'
# Next Trainer Agent — third-party components

This plugin embeds unmodified upstream projects (Goal v9 / CR-011):

- **pi-web v0.8.9** — `github.com/agegr/pi-web` @ `2a6e53710f6409e0cceb3de839a62f8cdf3ca3ca`,
  MIT, Copyright (c) 2026 agegr. See `LICENSES/pi-web-MIT.txt` and `pi-web/LICENSE`.
- **pi coding agent packages 0.84.2** — `github.com/earendil-works/pi`, npm packages
  `@earendil-works/pi-agent-core`, `pi-ai`, `pi-coding-agent`, `pi-tui` (plus transitive `pi-telemetry`),
  MIT declared per package. See `LICENSES/pi-agent-MIT.txt`.
- **Node.js 22.19.0 runtime** — `node` under `runtime/node/`, Node.js project license.
- **Next.js 16.3.1 / React 19.2.4** and other runtime dependencies inside `pi-web/node_modules`,
  each under its own upstream license recorded by the npm registry.

The launcher (`bin/next-trainer-pi-agent`, ELF linux-x64) is Next Trainer packaging glue: it only implements the
host runtime contract (READY/health) and supervises the unmodified pi-web server.
EOF

cat > "$STAGE/plugin.json" <<EOF
{
  "id": "next-trainer-pi-agent",
  "publisher": "next-trainer-project",
  "version": "$VERSION",
  "protocolVersion": "1",
  "hostCompatibility": ">=2.9.2 <4.0.0",
  "platforms": ["linux-x64"],
  "runtime": {
    "kind": "executable",
    "entrypoint": "bin/next-trainer-pi-agent",
    "buildNode": "22.19.0",
    "embeddedRuntime": "bun-1.4.0-launcher+node-22.19.0-runtime"
  },
  "ui": {
    "entrypoint": "ui/index.html",
    "extensionApi": "1",
    "placements": ["floating-panel"]
  },
  "bridge": { "requests": [], "streams": [] },
  "capabilities": ["server-ui", "custom-tools", "skills"],
  "permissions": ["training-config", "dataset-review", "caption-commit", "metrics-read", "artifacts-read", "external-civitai-read"],
  "package": {
    "sha256": "BUILD_TIME_VALUE",
    "signature": "TEST_OR_RELEASE_VALUE",
    "sbom": "sbom.cdx.json"
  },
  "installHooks": []
}
EOF

cat > "$STAGE/sbom.cdx.json" <<EOF
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "version": 1,
  "metadata": {
    "component": {
      "type": "application",
      "name": "next-trainer-pi-agent",
      "version": "$VERSION"
    }
  },
  "components": [
    {
      "type": "application",
      "name": "@agegr/pi-web",
      "version": "0.8.9",
      "purl": "pkg:npm/%40agegr/pi-web@0.8.9",
      "licenses": [{"license": {"id": "MIT"}}],
      "description": "Verbatim upstream source + production build; see LICENSES/pi-web-MIT.txt"
    },
    {"type": "library", "name": "pi-agent-core", "version": "0.84.2", "purl": "pkg:npm/%40earendil-works/pi-agent-core@0.84.2", "licenses": [{"license": {"id": "MIT"}}]},
    {"type": "library", "name": "pi-ai", "version": "0.84.2", "purl": "pkg:npm/%40earendil-works/pi-ai@0.84.2", "licenses": [{"license": {"id": "MIT"}}]},
    {"type": "library", "name": "pi-coding-agent", "version": "0.84.2", "purl": "pkg:npm/%40earendil-works/pi-coding-agent@0.84.2", "licenses": [{"license": {"id": "MIT"}}]},
    {"type": "library", "name": "pi-tui", "version": "0.84.2", "purl": "pkg:npm/%40earendil-works/pi-tui@0.84.2", "licenses": [{"license": {"id": "MIT"}}]},
    {"type": "library", "name": "next", "version": "16.3.1", "purl": "pkg:npm/next@16.3.1"},
    {"type": "library", "name": "react", "version": "19.2.4", "purl": "pkg:npm/react@19.2.4"},
    {"type": "library", "name": "node", "version": "22.19.0", "purl": "pkg:github/nodejs/node@v22.19.0"}
  ]
}
EOF

echo "[stage] copying pi-web tree (source + .next + pruned node_modules) ..."
cp -a "$W/src/pi-web" "$STAGE/pi-web"

# Next Trainer pi package (extensions + skills + manifest) + knowledge/template
# seeds. Dev-only artifacts (pi-package/test) are excluded.
echo "[stage] pi-package (extensions + skills + package.json) + seeds ..."
mkdir -p "$STAGE/pi-package"
cp -a "$PKG_ROOT/pi-package/extensions" "$STAGE/pi-package/extensions"
cp -a "$PKG_ROOT/pi-package/skills" "$STAGE/pi-package/skills"
cp "$PKG_ROOT/pi-package/package.json" "$STAGE/pi-package/package.json"
cp -a "$PKG_ROOT/seeds" "$STAGE/seeds"

OUT_ZIP=$PKG_ROOT/dist-marketplace/packages/next-trainer-pi-agent-${VERSION}-linux-x64.zip
rm -f "$OUT_ZIP"
python3 - "$STAGE" "$OUT_ZIP" <<'EOF'
import os
import stat
import sys
import time
import zipfile

stage, out = sys.argv[1], sys.argv[2]
files = []
for root, dirs, names in os.walk(stage):
    dirs.sort()
    for name in sorted(names):
        full = os.path.join(root, name)
        if os.path.islink(full):
            continue  # the package format forbids links
        files.append((os.path.relpath(full, stage).replace(os.sep, "/"), full))
files.sort()
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for rel, full in files:
        st = os.stat(full)
        info = zipfile.ZipInfo(rel, date_time=time.localtime(st.st_mtime)[:6])
        info.external_attr = ((stat.S_IMODE(st.st_mode) << 16) | 0o100000)
        info.compress_type = zipfile.ZIP_DEFLATED
        with open(full, "rb") as fh:
            z.writestr(info, fh.read())
print(f"[zip] entries={len(files)} out={out} bytes={os.path.getsize(out)}")
EOF

echo "STAGE OK"

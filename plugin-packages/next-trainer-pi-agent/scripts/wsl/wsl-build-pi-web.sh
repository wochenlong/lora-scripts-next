#!/usr/bin/env bash
# Dual-platform pipeline (CR-012): build pi-web for linux-x64 inside WSL.
#
# Usage:  bash wsl-build-pi-web.sh [source-tar]
#   source-tar  path to the pi-web source tar (no node_modules/.next);
#               default: <package root>/.runtime/linux-src.tar.gz
#
# Output:  $W/src/pi-web  (with .next + pruned linux node_modules)
#          $W/node-v22.19.0-linux-x64  (provisioned runtime)
#
# Notes:
#   - This distro has no xz binary -> Node .tar.gz is used.
#   - WSL NAT is flaky for large transfers -> npm ci retries on its cache.
#   - dist-types trees and the lockfile are handled exactly like the Windows
#     package (see scripts/build-pi-web-package.py).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

W=/tmp/nt-pi-linux
SRC_TAR="${1:-$PKG_ROOT/.runtime/linux-src.tar.gz}"

rm -rf "$W"
mkdir -p "$W"
cd "$W"

echo "=== [1/7] provision Node 22.19.0 linux-x64 ==="
if [ ! -x node-v22.19.0-linux-x64/bin/node ]; then
  # .tar.gz: this distro has no xz binary.
  curl -fsSL -o node.tar.gz https://nodejs.org/dist/v22.19.0/node-v22.19.0-linux-x64.tar.gz
  tar -xf node.tar.gz
fi
export PATH="$W/node-v22.19.0-linux-x64/bin:$PATH"
node -v
npm -v

echo "=== [2/7] unpack pi-web source ($SRC_TAR) ==="
if [ ! -f "$SRC_TAR" ]; then
  echo "missing source tar: $SRC_TAR" >&2
  exit 1
fi
mkdir -p src
tar -xzf "$SRC_TAR" -C src
cd src/pi-web

echo "=== [3/7] npm ci (full, linux platform, retrying on flaky WSL NAT) ==="
npm_ci_flags="--no-audit --no-fund --fetch-retries=6 --fetch-retry-mintimeout=2000 --fetch-retry-maxtimeout=60000 --fetch-timeout=600000"
attempt=0
until npm ci $npm_ci_flags; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 3 ]; then
    echo "npm ci failed after $attempt attempts"
    exit 1
  fi
  echo "npm ci attempt $attempt failed; retrying (npm cache resumes) ..."
  sleep 5
done

echo "=== [4/7] next build --webpack ==="
npm run build

echo "=== [5/7] npm prune --omit=dev + restore lockfile verbatim ==="
cp package-lock.json "$W/package-lock.orig"
npm prune --omit=dev --no-audit --no-fund
cp "$W/package-lock.orig" package-lock.json

echo "=== [6/7] strip dist-types ==="
find node_modules -type d -name dist-types -prune -exec rm -rf {} + 2>/dev/null || true
echo "dist-types remaining: $(find node_modules -type d -name dist-types | wc -l)"

echo "=== [7/7] smoke test: boot pi-web on 127.0.0.1:31141 ==="
export PI_WEB_NO_OPEN=1
mkdir -p "$W/home" "$W/agent" "$W/tmp"
export HOME="$W/home" PI_CODING_AGENT_DIR="$W/agent" TMPDIR="$W/tmp"
nohup node bin/pi-web.js -H 127.0.0.1 -p 31141 --no-open > "$W/pi-web.log" 2>&1 &
PWPID=$!
ok=0
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 2 http://127.0.0.1:31141/ || true)
  if [ "$code" != "000" ] && [ -n "$code" ]; then ok=1; break; fi
  sleep 1
done
if [ "$ok" = "1" ]; then
  echo "root http_code: $code"
  echo "root bytes: $(curl -s -m 5 http://127.0.0.1:31141/ | wc -c)"
  echo "sessions: $(curl -s -m 90 http://127.0.0.1:31141/api/sessions | head -c 200)"
else
  echo "SMOKE FAIL: pi-web did not answer; log tail:"
  tail -40 "$W/pi-web.log"
  exit 1
fi
kill "$PWPID" 2>/dev/null || true
sleep 1
pkill -f 'pi-web.js' 2>/dev/null || true
echo "BUILD OK"

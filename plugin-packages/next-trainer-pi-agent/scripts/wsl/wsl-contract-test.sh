#!/usr/bin/env bash
# Dual-platform pipeline (CR-012): launcher contract test on linux (WSL).
# Against the staged package: READY line, Bearer /health, uiUrl serving,
# and parent-death process-group shutdown (no orphaned pi-web tree).
#
# Usage:  bash wsl-contract-test.sh [out-file]
# Requires /tmp/nt-pi-linux/stage (from wsl-stage-linux-package.sh).
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

S=/tmp/nt-pi-linux/stage
D=/tmp/nt-pi-linux/contract-data
OUT="${1:-$PKG_ROOT/.runtime/wsl-contract.out}"
rm -rf "$D"
mkdir -p "$D" "$PKG_ROOT/.runtime"

TOKEN=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')
sleep 300 &
PARENT=$!

env NEXT_TRAINER_PLUGIN_DATA_ROOT="$D" \
    NEXT_TRAINER_SIDECAR_TOKEN="$TOKEN" \
    NEXT_TRAINER_PARENT_PID="$PARENT" \
    NEXT_TRAINER_SIDECAR_PORT=0 \
  "$S/bin/next-trainer-pi-agent" > "$D/launcher-stdout.log" 2> "$D/launcher-stderr.log" &
LAUNCHER=$!

{
  echo "launcher_pid: $LAUNCHER"
  echo "parent_pid: $PARENT"

  # 1) READY line within 120 s.
  ready=""
  for i in $(seq 1 120); do
    ready=$(grep -m1 '"type":"READY"' "$D/launcher-stdout.log" 2>/dev/null || true)
    [ -n "$ready" ] && break
    kill -0 "$LAUNCHER" 2>/dev/null || break
    sleep 1
  done
  if [ -z "$ready" ]; then
    echo "FAIL: no READY line"
    echo "--- stdout:"; cat "$D/launcher-stdout.log"
    echo "--- stderr:"; cat "$D/launcher-stderr.log"
    echo "--- pi-web.log tail:"; tail -20 "$D/pi-web.log" 2>/dev/null
    kill "$PARENT" 2>/dev/null
    exit 1
  fi
  echo "READY: $ready"

  PORT=$(echo "$ready" | python3 -c 'import sys,json; print(json.loads(sys.stdin.read())["port"])')
  UIURL=$(echo "$ready" | python3 -c 'import sys,json; print(json.loads(sys.stdin.read())["uiUrl"])')
  echo "port: $PORT  uiUrl: $UIURL"

  # 2) /health with Bearer token.
  health=$(curl -s -m 5 -w '\n%{http_code}' -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:$PORT/health")
  echo "health: $health"
  echo "$health" | grep -q 200 || { echo "FAIL: /health not 200"; exit 1; }

  # 3) uiUrl (pi-web) serves the app.
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$UIURL/")
  echo "uiUrl root: $code"
  [ "$code" = "200" ] || { echo "FAIL: uiUrl root not 200"; exit 1; }
  sessions=$(curl -s -m 90 "$UIURL/api/sessions")
  echo "sessions: $sessions"

  # 4) Parent death -> launcher shuts the whole pi-web process group down.
  kill "$PARENT" 2>/dev/null
  stopped=0
  for i in $(seq 1 20); do
    kill -0 "$LAUNCHER" 2>/dev/null || { stopped=1; break; }
    sleep 1
  done
  echo "launcher stopped after parent death: $stopped"
  sleep 2
  # Exact match (escaped dot, full path) to avoid pgrep -f self-matching the
  # test script's own command line.
  leftovers=$(pgrep -fc "node .*/pi-web/bin/pi-web\.js" 2>/dev/null || echo 0)
  echo "pi-web leftovers: $leftovers"
  if [ "$stopped" = "1" ] && [ "$leftovers" = "0" ]; then
    echo "CONTRACT OK"
  else
    echo "CONTRACT FAIL"
    exit 1
  fi
} > "$OUT" 2>&1
rc=$?
kill "$PARENT" 2>/dev/null
exit $rc

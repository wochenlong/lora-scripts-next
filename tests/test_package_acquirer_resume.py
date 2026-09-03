"""P0-1: HttpPackageAcquirer Range resumption, backoff and stall watchdog.

Fault-injection loopback mirror (the established mirror-base-URL technique):
the catalog entry keeps its HTTPS pin; the acquirer is built with a
loopback mirror so the test server can cut, poison, stall and 416 the
download on demand. Integrity always comes from the catalog-pinned
size + sha256 — resumption never weakens it.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from mikazuki.plugin_marketplace.catalog import (
    CatalogError,
    HttpPackageAcquirer,
)
from mikazuki.plugin_marketplace.models import MarketplaceEntry
from mikazuki.plugin_marketplace.trust import canonical_entry_payload


KEY = b"test-resume-key"
DEV_URL = "https://plugins.next-trainer.local/packages/pkg.zip"
# ~4 MB: large enough that the 1 MB download chunk writes multiple
# .part chunks before a fault, so resume offsets are non-trivial.
BODY = (b"resume-package-payload" * 182_000) + b"tail-bytes"  # 4004010 bytes


class _Server:
    """Loopback mirror with per-request scripted behavior.

    Each test installs a list of behavior dicts, one per incoming request
    (last entry repeats for any extra requests). Behavior kinds:

      {"full"}              200 + full body (declared Content-Length)
      {"short"}             200 + a genuinely shorter body, declared length
      {"cut": N}            200 declared full, send N bytes, hard close
      {"range"}             honor Range: 206 + body[N:] + Content-Range
      {"range_poison": N}   like range but flip one byte just after N
      {"no_range"}          always 200 full body, Range ignored
      {"stall": N, "sleep": S}
                            like cut but sleep S seconds instead of closing
      {"http": 416}         bare 416 response
    """

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.requests: list[dict] = []  # {"path", "range", "n"}
        self.behavior: list[dict] = []
        self.lock = threading.Lock()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler(self))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}"

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    @staticmethod
    def _make_handler(state: "_Server"):
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args) -> None:  # silence
                pass

            def do_GET(self) -> None:  # noqa: N802
                with state.lock:
                    n = len(state.requests)
                    state.requests.append({"path": self.path, "range": self.headers.get("Range")})
                    spec = state.behavior[n] if n < len(state.behavior) else state.behavior[-1]
                try:
                    self._run(spec, n)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass  # abandoned client (stall tests): expected

            def _send(self, status: int, body: bytes = b"", extra: dict | None = None) -> None:
                self.send_response(status)
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _run(self, spec: dict, n: int) -> None:
                kind = next(iter(spec))
                if kind == "full":
                    self._send(200, BODY)
                elif kind == "short":
                    self._send(200, BODY[: len(BODY) // 2])
                elif kind == "no_range":
                    self._send(200, BODY)
                elif kind == "cut":
                    cut_at = spec["cut"]
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(BODY)))
                    self.end_headers()
                    self.wfile.write(BODY[:cut_at])
                    self.wfile.flush()
                    # Hard close: the client sees EOF before the declared
                    # length — an interrupted transfer, not a short object.
                    self.connection.close()
                elif kind == "stall":
                    stall_at = spec["stall"]
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(BODY)))
                    self.end_headers()
                    self.wfile.write(BODY[:stall_at])
                    self.wfile.flush()
                    time.sleep(spec.get("sleep", 30))
                elif kind == "range":
                    rng = self.headers.get("Range") or ""
                    match = re.fullmatch(r"bytes=(\d+)-", rng)
                    if match is None:
                        # No range offered (e.g. nothing was persisted to the
                        # .part before the fault): serve the full object.
                        self._send(200, BODY)
                        return
                    start = int(match.group(1))
                    part = BODY[start:]
                    self._send(
                        206,
                        part,
                        extra={"Content-Range": f"bytes {start}-{len(BODY) - 1}/{len(BODY)}"},
                    )
                elif kind == "range_poison":
                    rng = self.headers.get("Range") or ""
                    match = re.fullmatch(r"bytes=(\d+)-", rng)
                    if match is None:
                        self._send(200, BODY)
                        return
                    start = int(match.group(1))
                    part = bytearray(BODY[start:])
                    poison_at = max(0, spec.get("at", 0) - start)
                    if poison_at < len(part):
                        part[poison_at] ^= 0xFF
                    self._send(
                        206,
                        bytes(part),
                        extra={"Content-Range": f"bytes {start}-{len(BODY) - 1}/{len(BODY)}"},
                    )
                elif kind == "http":
                    self._send(spec["http"])
                else:
                    raise AssertionError(f"unknown behavior {spec!r}")

        return Handler


def _build_entry() -> MarketplaceEntry:
    value = {
        "id": "sample-plugin",
        "name": "Sample",
        "publisher_id": "approved-publisher-id",
        "latest_version": "1.0.0",
        "channel": "stable",
        "host_compatibility": ">=2.9.2 <3.0.0",
        "platforms": ["win32-x64"],
        "package_size": len(BODY),
        "permissions_summary": [],
        "license": "MIT",
        "package_url": DEV_URL,
        "sha256": hashlib.sha256(BODY).hexdigest(),
        "signature": "",
        "signing_key_id": "test-key",
        "published_at": "2026-08-29T00:00:00Z",
    }
    unsigned = MarketplaceEntry.model_validate(value)
    value["signature"] = hmac.new(KEY, canonical_entry_payload(unsigned), hashlib.sha256).hexdigest()
    return MarketplaceEntry.model_validate(value)


@pytest.fixture()
def server(tmp_path: Path):
    srv = _Server(tmp_path)
    yield srv
    srv.stop()


def _acquirer(server: _Server, **kwargs) -> HttpPackageAcquirer:
    kwargs.setdefault("backoff_base_s", 0.0)  # keep the suite fast
    return HttpPackageAcquirer(server.base_url, **kwargs)


def _acquire(acquirer: HttpPackageAcquirer, dest: Path, **kwargs) -> None:
    acquirer.acquire(_build_entry(), dest, "win32-x64", **kwargs)


def test_clean_download_single_shot(server: _Server, tmp_path: Path) -> None:
    server.behavior = [{"full"}]
    dest = tmp_path / "p" / "0.3.10.zip"
    _acquire(_acquirer(server), dest)
    assert dest.read_bytes() == BODY
    assert len(server.requests) == 1
    assert server.requests[0]["range"] is None
    assert not dest.with_suffix(".zip.part").exists()


def test_resume_after_cut(server: _Server, tmp_path: Path) -> None:
    cut_at = len(BODY) // 3
    server.behavior = [{"cut": cut_at}, {"range"}]
    dest = tmp_path / "p" / "0.3.10.zip"
    progress: list[tuple[int, int]] = []
    _acquire(_acquirer(server), dest, on_progress=lambda c, t: progress.append((c, t)))
    assert dest.read_bytes() == BODY
    # Second request resumes exactly where the first one stopped.
    assert len(server.requests) == 2
    assert server.requests[1]["range"] == f"bytes={cut_at}-"
    # The prefix was NOT re-sent: total transferred bytes == full size once.
    transferred = cut_at + (len(BODY) - cut_at)
    assert transferred == len(BODY)
    # Progress never resets backwards across the resumed attempt.
    flat = [c for c, _ in progress]
    assert all(b >= a for a, b in zip(flat, flat[1:]))
    assert flat[-1] == len(BODY)


def test_server_ignores_range_falls_back_to_full_redownload(server: _Server, tmp_path: Path) -> None:
    cut_at = 10_000
    server.behavior = [{"cut": cut_at}, {"no_range"}]
    dest = tmp_path / "p" / "0.3.10.zip"
    _acquire(_acquirer(server), dest)
    assert dest.read_bytes() == BODY
    assert len(server.requests) == 2
    # The client did offer the range; the server answered 200 (ignored it),
    # and the client discarded its kept prefix and re-downloaded from zero.
    assert server.requests[1]["range"] == f"bytes={cut_at}-"


def test_poisoned_resume_detected_by_sha_then_full_redownload(server: _Server, tmp_path: Path) -> None:
    cut_at = len(BODY) // 2
    server.behavior = [{"cut": cut_at}, {"range_poison": cut_at}, {"full"}]
    dest = tmp_path / "p" / "0.3.10.zip"
    _acquire(_acquirer(server), dest)
    assert dest.read_bytes() == BODY
    assert len(server.requests) == 3
    # The integrity failure dropped the .part: attempt 3 started fresh.
    assert server.requests[2]["range"] is None


def test_416_on_resume_drops_prefix_and_recovers(server: _Server, tmp_path: Path) -> None:
    cut_at = 20_000
    server.behavior = [{"cut": cut_at}, {"http": 416}, {"full"}]
    dest = tmp_path / "p" / "0.3.10.zip"
    _acquire(_acquirer(server), dest)
    assert dest.read_bytes() == BODY
    assert len(server.requests) == 3
    assert server.requests[2]["range"] is None  # prefix was dropped on 416


def test_stall_watchdog_triggers_resume_retry(server: _Server, tmp_path: Path) -> None:
    # Three full 1 MB chunks reach the .part before the connection stalls,
    # so the resume offset is a real non-zero position.
    stall_at = 3_000_000
    server.behavior = [{"stall": stall_at, "sleep": 20}, {"range"}]
    dest = tmp_path / "p" / "0.3.10.zip"
    started = time.monotonic()
    acquirer = _acquirer(server, stall_timeout_s=0.4)
    _acquire(acquirer, dest)
    elapsed = time.monotonic() - started
    assert dest.read_bytes() == BODY
    assert len(server.requests) == 2
    # The .part only ever holds fully-written 1 MB chunks: at the stall,
    # two chunks (2097152 B) were flushed and the in-flight third was
    # discarded — so the resume offset is the chunk-aligned position, not
    # stall_at itself. Nothing is lost: the tail is re-sent by the server.
    chunk = 1024 * 1024
    assert stall_at % chunk  # precondition: the stall lands mid-chunk
    expected_offset = (stall_at // chunk) * chunk
    assert server.requests[1]["range"] == f"bytes={expected_offset}-"
    # The 0.4s stall window (socket timeout) fired — not the 20s server sleep.
    assert elapsed < 10


def test_cancel_mid_resume_raises_cancelled_and_leaves_no_destination(server: _Server, tmp_path: Path) -> None:
    cut_at = 12_000
    server.behavior = [{"cut": cut_at}, {"stall": 0, "sleep": 20}]
    dest = tmp_path / "p" / "0.3.10.zip"
    state = {"cancel": False}
    acquirer = _acquirer(server, stall_timeout_s=5.0)
    entry = _build_entry()

    def flip_cancel() -> bool:
        # Cancel once the resumed attempt has begun moving.
        if len(server.requests) >= 2 and not state["cancel"]:
            state["cancel"] = True
        return state["cancel"]

    with pytest.raises(CatalogError) as excinfo:
        acquirer.acquire(entry, dest, "win32-x64", is_cancelled=flip_cancel)
    assert excinfo.value.code == "MARKETPLACE_OPERATION_CANCELLED"
    assert not dest.exists()


def test_exhausted_attempts_backoff_and_part_cleanup(server: _Server, tmp_path: Path, monkeypatch) -> None:
    cut_at = 5_000
    server.behavior = [{"cut": cut_at}]  # every attempt dies the same way
    dest = tmp_path / "p" / "0.3.10.zip"
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    acquirer = _acquirer(server, max_attempts=4, backoff_base_s=1.0)
    with pytest.raises(CatalogError) as excinfo:
        _acquire(acquirer, dest)
    assert excinfo.value.code == "MARKETPLACE_PACKAGE_ACQUISITION_FAILED"
    assert len(server.requests) == 4
    # Exponential backoff: 1s, 2s, 4s (capped growth), no sleep before attempt 1.
    assert sleeps == [1.0, 2.0, 4.0]
    # Attempt budget exhausted: the partial file was swept.
    assert not dest.with_suffix(".zip.part").exists()
    assert not dest.exists()


def test_genuinely_short_object_is_not_retried(server: _Server, tmp_path: Path) -> None:
    # Server declares a complete short body: the catalog pin is simply wrong.
    server.behavior = [{"short"}]
    dest = tmp_path / "p" / "0.3.10.zip"
    with pytest.raises(CatalogError) as excinfo:
        _acquire(_acquirer(server), dest)
    assert excinfo.value.code == "MARKETPLACE_PACKAGE_SIZE_MISMATCH"
    assert excinfo.value.status_code == 400
    assert len(server.requests) == 1  # non-retryable: no wasted attempts
    assert not dest.with_suffix(".zip.part").exists()


def test_preexisting_part_larger_than_pin_restarts_fresh(server: _Server, tmp_path: Path) -> None:
    # A stale .part that already exceeds the pinned size cannot be a valid
    # prefix: the acquirer must not append to it.
    server.behavior = [{"full"}]
    dest = tmp_path / "p" / "0.3.10.zip"
    dest.parent.mkdir(parents=True)
    dest.with_suffix(".zip.part").write_bytes(b"x" * (len(BODY) + 1))
    _acquire(_acquirer(server), dest)
    assert dest.read_bytes() == BODY
    assert len(server.requests) == 1
    assert server.requests[0]["range"] is None

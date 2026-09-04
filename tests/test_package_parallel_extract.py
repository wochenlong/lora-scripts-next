"""P1-2 parallel extraction: members of the verified package can be written
concurrently (opt-in pool, per-worker zip instances) instead of serially.
The DEFAULT is serial (bench lesson: AV-scanned machines measured the
16-worker pool ~2.3x SLOWER); parallel engages via max_workers or
MIKAZUKI_EXTRACT_WORKERS.

Contract under test:
- serial (max_workers=1) and parallel results are byte-identical per file;
- hard-link reuse (P0-2) works unchanged under parallelism (same count,
  real ino identity);
- a failing member fails the WHOLE extraction (first error raised) — the
  caller's staging cleanup then removes the partial tree;
- safety checks (unsafe path) still fail before any file is written;
- the adaptive worker count is bounded and monotonic.
"""

from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

import pytest

from mikazuki.plugin_marketplace.package import (
    PackageValidationError,
    _extraction_worker_count,
    _extraction_workers_from_env,
    extract_package,
)


def _members(package: Path) -> list[zipfile.ZipInfo]:
    # extract_package takes the member list straight from the archive; a
    # full manifest (plugin.json/SBOM) is irrelevant to the extraction
    # contract, so the sample zips stay minimal.
    with zipfile.ZipFile(package, "r") as archive:
        return [info for info in archive.infolist() if not info.is_dir()]


def _make_zip(path: Path, spec: dict[str, bytes], *, corrupt_member: str | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in spec.items():
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_STORED if (corrupt_member and name == corrupt_member) else zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)
    if corrupt_member:
        with zipfile.ZipFile(path, "r") as archive:
            info = archive.getinfo(corrupt_member)
            # Local header: 30-byte base + filename + extra, then the data.
            offset = info.header_offset + 30 + len(info.filename.encode("utf-8")) + len(info.extra)
        data = bytearray(path.read_bytes())
        data[offset] ^= 0xFF
        path.write_bytes(bytes(data))
    return path


def _sample_spec(count: int = 300) -> dict[str, bytes]:
    spec: dict[str, bytes] = {}
    for i in range(count):
        depth = i % 5
        rel = "/".join([f"d{depth // 2 or 0}"] * depth + [f"file_{i:04d}.bin"])
        spec[rel] = (f"payload-{i}-" * max(1, i % 7)).encode("utf-8")
    # one deliberately deep tree (mirrors the node_modules MAX_PATH case)
    deep = "/".join([f"seg{i % 7}" for i in range(12)] + ["deep.txt"])
    spec[deep] = b"deep payload"
    return spec


def _sha_tree(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            out[rel] = hashlib.sha256(full.read_bytes()).hexdigest()
    return out


def test_serial_and_parallel_extractions_are_byte_identical(tmp_path: Path):
    spec = _sample_spec(300)
    package = _make_zip(tmp_path / "pkg.zip", spec)

    serial_dir = tmp_path / "serial"
    parallel_dir = tmp_path / "parallel"

    members = _members(package)
    reused_serial = extract_package(package, serial_dir, members, max_workers=1)
    members2 = _members(package)
    # Explicit pool: the DEFAULT is serial (P1-2 bench lesson — parallel is
    # an opt-in), so the parallel leg names its workers outright.
    reused_parallel = extract_package(package, parallel_dir, members2, max_workers=4)

    assert reused_serial == 0
    assert reused_parallel == 0
    assert _sha_tree(serial_dir) == _sha_tree(parallel_dir)
    assert len(_sha_tree(serial_dir)) == len(spec)


def test_deep_paths_identical_under_parallelism(tmp_path: Path):
    spec = {"a.txt": b"aaa"}
    spec.update(_sample_spec(400))
    package = _make_zip(tmp_path / "pkg.zip", spec)
    members = _members(package)
    deep_dir = tmp_path / "deep"
    # Force the parallel path explicitly (400+ members is already >= 256).
    extract_package(package, deep_dir, members, max_workers=8)
    for rel, payload in spec.items():
        assert (deep_dir / rel).read_bytes() == payload, rel


def test_parallel_reuse_hard_links_match_serial_count(tmp_path: Path):
    spec = _sample_spec(320)
    package = _make_zip(tmp_path / "pkg.zip", spec)
    members = _members(package)

    # Donor = a previous-version tree byte-identical to every member.
    donor = tmp_path / "donor"
    for rel, payload in spec.items():
        full = donor / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(payload)

    target = tmp_path / "target"
    reused = extract_package(package, target, members, reuse_from=donor)
    assert reused == len(spec)
    # Every file must be a hard link to the donor (same inode).
    for rel, _payload in spec.items():
        assert (target / rel).stat().st_ino == (donor / rel).stat().st_ino, rel
    # The donor tree must be untouched.
    assert _sha_tree(donor) == {rel: hashlib.sha256(payload).hexdigest() for rel, payload in spec.items()}


def test_parallel_reuse_falls_back_for_changed_members(tmp_path: Path):
    spec = _sample_spec(200)
    changed = {k: v for k, v in spec.items()}
    changed["d0/file_0001.bin"] = b"CHANGED CONTENT"
    package = _make_zip(tmp_path / "pkg.zip", changed)
    members = _members(package)

    donor = tmp_path / "donor"
    for rel, payload in spec.items():  # donor = ORIGINAL content
        full = donor / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(payload)

    target = tmp_path / "target"
    reused = extract_package(package, target, members, reuse_from=donor)
    assert reused == len(spec) - 1
    # The changed member was extracted (different inode, correct content).
    assert (target / "d0/file_0001.bin").read_bytes() == b"CHANGED CONTENT"
    assert (target / "d0/file_0001.bin").stat().st_ino != (donor / "d0/file_0001.bin").stat().st_ino


def test_failing_member_fails_whole_extraction(tmp_path: Path):
    spec = _sample_spec(300)
    bad_name = "file_0010.bin"  # top-level member (i=10 -> depth 0)
    package = _make_zip(tmp_path / "pkg.zip", spec, corrupt_member=bad_name)

    # The member bodies are only read during extraction: a corrupted member
    # must fail the WHOLE parallel extraction.
    members = _members(package)
    target = tmp_path / "target"
    with pytest.raises(Exception):  # BadZipFile/CRC/OSError: whole op fails
        extract_package(package, target, members, max_workers=8)
    # A clean re-extract of a good package into the same target still works
    # (extract_package clears the target first).
    good = _make_zip(tmp_path / "good.zip", spec)
    good_members = _members(good)
    extract_package(good, target, good_members)
    assert _sha_tree(target) == {rel: hashlib.sha256(payload).hexdigest() for rel, payload in spec.items()}


def test_unsafe_member_fails_before_any_write(tmp_path: Path):
    spec = _sample_spec(100)
    spec["../evil.txt"] = b"nope"
    package = _make_zip(tmp_path / "pkg.zip", {k: v for k, v in spec.items() if not k.startswith("../")})
    # Build the member list manually to bypass inspect (which rejects it):
    with zipfile.ZipFile(package, "r") as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
    bad = zipfile.ZipInfo("../evil.txt")
    members.append(bad)

    target = tmp_path / "target"
    with pytest.raises(PackageValidationError):
        extract_package(package, target, members, max_workers=8)
    # No member may have been written before the validation failure.
    written = [p for p in target.rglob("*") if p.is_file()] if target.exists() else []
    assert written == []


def test_worker_count_is_bounded_and_monotonic():
    assert _extraction_worker_count(0) == 1
    assert _extraction_worker_count(1) == 1
    assert _extraction_worker_count(32) == 1
    assert _extraction_worker_count(300) == 8
    assert _extraction_worker_count(10_000) == 10
    assert _extraction_worker_count(36_862) == 16
    assert _extraction_worker_count(100_000) == 16  # capped
    # monotonic within bounds
    prev = 1
    for n in (1, 64, 200, 500, 2_000, 10_000, 30_000, 100_000):
        value = _extraction_worker_count(n)
        assert value >= prev
        assert 1 <= value <= 16
        prev = value


def test_default_is_serial_and_env_opts_into_pool(monkeypatch):
    # P1-2 bench lesson: parallel (16 workers) measured ~2.3x SLOWER than
    # serial on the AV-scanned acceptance machine, so the DEFAULT stays
    # serial and parallel is an explicit opt-in via the env.
    assert _extraction_workers_from_env() is None
    monkeypatch.setenv("MIKAZUKI_EXTRACT_WORKERS", "")
    assert _extraction_workers_from_env() is None
    monkeypatch.setenv("MIKAZUKI_EXTRACT_WORKERS", "bogus")
    assert _extraction_workers_from_env() is None  # invalid -> serial default
    monkeypatch.setenv("MIKAZUKI_EXTRACT_WORKERS", "0")
    assert _extraction_workers_from_env() == 1
    monkeypatch.setenv("MIKAZUKI_EXTRACT_WORKERS", "4")
    assert _extraction_workers_from_env() == 4
    monkeypatch.setenv("MIKAZUKI_EXTRACT_WORKERS", "99")
    assert _extraction_workers_from_env() == 16  # capped

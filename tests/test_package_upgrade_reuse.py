"""P0-2: version-upgrade extraction reuses byte-identical files via hard links.

extract_package(reuse_from=...) links members from a previous version's
installed directory when size + head sample + full CRC32 all agree; any
mismatch or link failure falls back to a normal extraction, and the donor
tree is only ever read (rollback stays intact).
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from mikazuki.plugin_marketplace.package import extract_package

from test_plugin_marketplace import FakeRuntime, build_package, manager_for, signed_entry

PLUGIN_ID = "next-trainer-pi-agent"

SHARED_BIG = (b"shared-big-file-content-" * 4_000)  # 128 KB
OLD_B = b"old-B-content"
NEW_B = b"new-B-content-changed-and-longer"


def _make_package(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def _members(path: Path) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(path, "r") as archive:
        return [item for item in archive.infolist() if not item.is_dir()]


def _make_trees(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, Path], dict[str, Path]]:
    """v1 installed (donor) + v2 package; v2 shares A, changes B, adds E, keeps empty D."""
    pkg1 = _make_package(
        tmp_path / "v1.zip",
        {
            "plugin.json": b'{"v": "1"}',
            "lib/a.bin": SHARED_BIG,
            "lib/b.bin": OLD_B,
            "only-v1.txt": b"gone in v2",
            "empty.txt": b"",
        },
    )
    donor = tmp_path / "donor"
    extract_package(pkg1, donor, _members(pkg1))
    pkg2 = _make_package(
        tmp_path / "v2.zip",
        {
            "plugin.json": b'{"v": "2"}',
            "lib/a.bin": SHARED_BIG,
            "lib/b.bin": NEW_B,
            "only-v2.txt": b"new in v2",
            "empty.txt": b"",
        },
    )
    target = tmp_path / "target"
    return pkg2, donor, target, {
        "shared": donor / "lib" / "a.bin",
        "changed": donor / "lib" / "b.bin",
        "empty": donor / "empty.txt",
    }, {
        "shared": target / "lib" / "a.bin",
        "changed": target / "lib" / "b.bin",
        "new": target / "only-v2.txt",
        "empty": target / "empty.txt",
    }


def test_identical_members_are_hard_linked(tmp_path: Path) -> None:
    pkg2, donor, target, donor_paths, target_paths = _make_trees(tmp_path)
    reused = extract_package(pkg2, target, _members(pkg2), reuse_from=donor)

    # A is reused; B (changed), E (new) and the empty member are not.
    assert reused == 1
    assert os.stat(donor_paths["shared"]).st_ino == os.stat(target_paths["shared"]).st_ino
    assert os.stat(target_paths["shared"]).st_nlink >= 2
    assert os.stat(donor_paths["changed"]).st_ino != os.stat(target_paths["changed"]).st_ino
    assert target_paths["changed"].read_bytes() == NEW_B
    assert target_paths["new"].read_bytes() == b"new in v2"
    assert target_paths["empty"].read_bytes() == b""
    # Deleted member is gone from the new tree.
    assert not (target / "only-v1.txt").exists()


def test_tampered_donor_middle_byte_is_not_reused(tmp_path: Path) -> None:
    pkg2, donor, target, donor_paths, _ = _make_trees(tmp_path)
    # Same size, same head 64 KB, same tail: only the full CRC can catch this.
    payload = bytearray(donor_paths["shared"].read_bytes())
    payload[len(payload) // 2] ^= 0xFF
    donor_paths["shared"].write_bytes(bytes(payload))

    reused = extract_package(pkg2, target, _members(pkg2), reuse_from=donor)

    assert reused == 0
    assert (target / "lib" / "a.bin").read_bytes() == SHARED_BIG
    assert os.stat(donor_paths["shared"]).st_ino != os.stat(target / "lib" / "a.bin").st_ino


def test_hardlink_failure_falls_back_to_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg2, donor, target, _, target_paths = _make_trees(tmp_path)

    def _boom(src, dst):
        raise OSError(31, "cross-device link")

    monkeypatch.setattr(os, "link", _boom)

    reused = extract_package(pkg2, target, _members(pkg2), reuse_from=donor)
    assert reused == 0
    assert (target / "lib" / "a.bin").read_bytes() == SHARED_BIG
    assert (target / "lib" / "b.bin").read_bytes() == NEW_B


def test_missing_reuse_root_behaves_like_plain_extract(tmp_path: Path) -> None:
    pkg2, donor, target, _, target_paths = _make_trees(tmp_path)
    reused = extract_package(pkg2, target, _members(pkg2), reuse_from=tmp_path / "no-such-dir")
    assert reused == 0
    assert target_paths["shared"].read_bytes() == SHARED_BIG
    assert target_paths["changed"].read_bytes() == NEW_B


def test_donor_tree_is_never_modified(tmp_path: Path) -> None:
    pkg2, donor, target, donor_paths, _ = _make_trees(tmp_path)
    before = {p: p.stat().st_mtime_ns for p in donor_paths.values()}
    extract_package(pkg2, target, _members(pkg2), reuse_from=donor)
    after = {p: p.stat().st_mtime_ns for p in donor_paths.values()}
    assert before == after
    assert donor_paths["shared"].read_bytes() == SHARED_BIG


def test_deep_beyond_max_path_member_is_reused(tmp_path: Path) -> None:
    """Deep node_modules-style members whose plain path exceeds Windows
    MAX_PATH must still be detected as reusable: the donor stat has to run
    through the raw (\\?\\) path or every deep member silently degrades to a
    full re-extract (caught by the 0.3.10 loopback E2E census: 8,590 deep
    files unlinked before the fix)."""
    deep_rel = "/".join("abcdefghijklmno" for _ in range(12)) + "/deep-file.bin"
    content = b"deep-shared-content-" * 500
    pkg1 = _make_package(tmp_path / "v1.zip", {"shallow.txt": b"x", deep_rel: content})
    donor = tmp_path / "donor"
    extract_package(pkg1, donor, _members(pkg1))
    # On Windows the plain donor path is longer than MAX_PATH (that is the
    # point of this test); on POSIX it is a legal path and the assertions
    # below hold trivially.
    donor_file = donor / Path(*deep_rel.split("/"))
    if os.name == "nt":
        assert len(str(donor_file)) > 260
    pkg2 = _make_package(tmp_path / "v2.zip", {"shallow.txt": b"changed", deep_rel: content})
    target = tmp_path / "target"
    reused = extract_package(pkg2, target, _members(pkg2), reuse_from=donor)

    from mikazuki.plugin_marketplace.package import _raw_path

    dest = target / Path(*deep_rel.split("/"))
    assert reused == 1
    assert os.stat(_raw_path(dest)).st_ino == os.stat(_raw_path(donor_file)).st_ino
    assert os.stat(_raw_path(dest)).st_nlink >= 2


def test_manager_upgrade_hardlinks_shared_members_between_version_dirs(tmp_path: Path) -> None:
    root = tmp_path / "marketplace-root"
    manager, key = manager_for(root, runtime=FakeRuntime())
    packages = tmp_path / "packages"
    packages.mkdir()
    v1 = build_package(packages, version="0.3.3")
    v2 = build_package(packages, version="0.3.4")
    manager.install(signed_entry(v1, key, version="0.3.3"), v1)
    manager.install(signed_entry(v2, key, version="0.3.4"), v2)

    old = manager.paths.version_dir(PLUGIN_ID, "0.3.3")
    new = manager.paths.version_dir(PLUGIN_ID, "0.3.4")
    # build_package keeps these four members byte-identical across versions.
    for rel in ("bin/next-trainer-pi-sidecar.exe", "ui/index.js", "sbom.cdx.json", "LICENSE"):
        a, b = old / rel, new / rel
        assert os.stat(a).st_ino == os.stat(b).st_ino, rel
        assert os.stat(b).st_nlink >= 2, rel
    # The version-dependent manifest is a fresh file.
    assert os.stat(old / "plugin.json").st_ino != os.stat(new / "plugin.json").st_ino
    # The old version directory is untouched (rollback source of truth).
    assert b'"version": "0.3.3"' in (old / "plugin.json").read_bytes() or b'"0.3.3"' in (old / "plugin.json").read_bytes()

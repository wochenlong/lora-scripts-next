"""Vendor bundle: offline pinned-source distribution end to end."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from mikazuki.engines.vendor_bundle import (
    ensure_vendor_source,
    find_vendor_bundle,
    snapshot_matches,
)


def _make_bundle(project: Path, dirs: dict[str, dict[str, str]], name: str = "vendor-bundle.zip") -> Path:
    vendor = project / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    bundle = vendor / name
    with zipfile.ZipFile(bundle, "w") as zf:
        for dirname, files in dirs.items():
            for rel, content in files.items():
                zf.writestr(f"{dirname}/{rel}", content)
    return bundle


FULL_SHA = "87819818975e08167cda8a6f615776e46e889f80"


class TestEnsureVendorSource:
    def test_extracts_bundle_when_dir_missing(self, tmp_path: Path):
        _make_bundle(tmp_path, {"musubi-tuner": {"src/musubi_tuner/__init__.py": "", ".source_commit": FULL_SHA + "\n"}})
        result = ensure_vendor_source(tmp_path, "musubi-tuner")
        assert result == (tmp_path / "vendor" / "musubi-tuner").resolve()
        assert (result / "src" / "musubi_tuner").is_dir()

    def test_existing_dir_wins_and_bundle_stays_packed(self, tmp_path: Path):
        existing = tmp_path / "vendor" / "musubi-tuner"
        existing.mkdir(parents=True)
        _make_bundle(tmp_path, {"anima_lora": {"train.py": "print(1)\n"}})
        assert ensure_vendor_source(tmp_path, "musubi-tuner") == existing.resolve()
        assert not (tmp_path / "vendor" / "anima_lora").exists()

    def test_no_bundle_returns_none(self, tmp_path: Path):
        assert ensure_vendor_source(tmp_path, "musubi-tuner") is None
        assert find_vendor_bundle(tmp_path) is None

    def test_extracts_only_once_per_bundle(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _make_bundle(tmp_path, {"anima_lora": {"train.py": "print(1)\n"}})
        import mikazuki.engines.vendor_bundle as vb

        calls = []
        real_extract = vb.extract_vendor_bundle

        def spy(*args, **kwargs):
            calls.append(1)
            return real_extract(*args, **kwargs)

        monkeypatch.setattr(vb, "extract_vendor_bundle", spy)
        assert ensure_vendor_source(tmp_path, "musubi-tuner") is None  # extracted, but dir absent
        assert ensure_vendor_source(tmp_path, "musubi-tuner") is None
        assert calls == [1]

    def test_replaced_bundle_never_overwrites_extracted_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        bundle = _make_bundle(tmp_path, {"anima_lora": {"train.py": "print(1)\n"}})
        assert ensure_vendor_source(tmp_path, "anima_lora") is not None
        import mikazuki.engines.vendor_bundle as vb

        calls = []
        real_extract = vb.extract_vendor_bundle

        def spy(*args, **kwargs):
            calls.append(1)
            return real_extract(*args, **kwargs)

        monkeypatch.setattr(vb, "extract_vendor_bundle", spy)
        bundle.write_bytes(b"different-content-now")
        result = ensure_vendor_source(tmp_path, "anima_lora")
        # One-shot contract: existing dir is returned as-is, never re-extracted.
        assert result == (tmp_path / "vendor" / "anima_lora").resolve()
        assert calls == []
        assert (result / "train.py").read_text(encoding="utf-8") == "print(1)\n"

    def test_manual_dir_with_bundle_warns_but_wins(self, tmp_path: Path):
        manual = tmp_path / "vendor" / "musubi-tuner"
        manual.mkdir(parents=True)
        _make_bundle(tmp_path, {"musubi-tuner": {"src/musubi_tuner/__init__.py": ""}})
        logs: list[str] = []
        result = ensure_vendor_source(tmp_path, "musubi-tuner", log=logs.append)
        assert result == manual.resolve()
        assert any("不覆盖" in line for line in logs)
        # Bundle was not extracted over the manual dir.
        assert not (manual / "src").exists()

    def test_tar_rejects_link_escaping_vendor(self, tmp_path: Path):
        import io
        import tarfile

        vendor = tmp_path / "vendor"
        vendor.mkdir()
        bundle = vendor / "vendor-bundle.tar"
        with tarfile.open(bundle, "w") as tf:
            link = tarfile.TarInfo("anima_lora/evil")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../outside"
            tf.addfile(link)
        import mikazuki.engines.vendor_bundle as vb

        with pytest.raises(ValueError):
            vb.extract_vendor_bundle(bundle, vendor)


class TestSnapshotMatches:
    def test_full_sha_recorded_with_prefix_request(self, tmp_path: Path):
        (tmp_path / ".source_commit").write_text(FULL_SHA + "\n", encoding="utf-8")
        assert snapshot_matches(tmp_path, FULL_SHA)
        assert snapshot_matches(tmp_path, "8781981")
        assert snapshot_matches(tmp_path, FULL_SHA[:7])
        assert not snapshot_matches(tmp_path, "deadbeef")
        assert not snapshot_matches(tmp_path, "")

    def test_truncated_or_malformed_marker_rejected(self, tmp_path: Path):
        (tmp_path / ".source_commit").write_text("8781981\n", encoding="utf-8")
        assert not snapshot_matches(tmp_path, FULL_SHA)
        (tmp_path / ".source_commit").write_text("8\n", encoding="utf-8")
        assert not snapshot_matches(tmp_path, FULL_SHA)
        (tmp_path / ".source_commit").write_text("not-a-sha-at-all-not-a-sha-at-all-1234567\n", encoding="utf-8")
        assert not snapshot_matches(tmp_path, FULL_SHA)


class TestMusubiResolveViaBundle:
    def test_resolve_picks_vendor_source_without_git(self, tmp_path: Path):
        _make_bundle(tmp_path, {"musubi-tuner": {"src/musubi_tuner/__init__.py": "", ".source_commit": FULL_SHA + "\n"}})
        from mikazuki.engines.musubi.settings import resolve_install_source_root

        result = resolve_install_source_root(tmp_path, None, FULL_SHA)
        assert result == (tmp_path / "vendor" / "musubi-tuner").resolve()

    def test_non_git_source_with_mismatched_marker_is_skipped(self, tmp_path: Path):
        vendor_src = tmp_path / "vendor" / "musubi-tuner" / "src" / "musubi_tuner"
        vendor_src.mkdir(parents=True)
        (tmp_path / "vendor" / "musubi-tuner" / ".source_commit").write_text(
            "0000000000000000000000000000000000000000\n", encoding="utf-8"
        )
        from mikazuki.engines.musubi.settings import resolve_install_source_root

        with pytest.raises(ValueError, match="未找到 musubi-tuner 源码"):
            resolve_install_source_root(tmp_path, None, FULL_SHA)

    def test_non_git_source_without_marker_is_skipped_when_pinned(self, tmp_path: Path):
        vendor_src = tmp_path / "vendor" / "musubi-tuner" / "src" / "musubi_tuner"
        vendor_src.mkdir(parents=True)
        from mikazuki.engines.musubi.settings import resolve_install_source_root

        with pytest.raises(ValueError, match="未找到 musubi-tuner 源码"):
            resolve_install_source_root(tmp_path, None, FULL_SHA)
        # Unpinned installs still accept the plain package tree.
        result = resolve_install_source_root(tmp_path, None, None)
        assert result == (tmp_path / "vendor" / "musubi-tuner").resolve()

    def _init_git_source(self, path: Path, sentinel: str) -> str:
        import subprocess

        (path / "src" / "musubi_tuner").mkdir(parents=True)
        (path / "src" / "musubi_tuner" / "__init__.py").write_text("", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        subprocess.run(["git", "-C", str(path), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(path), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", sentinel],
            check=True,
        )
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()

    def test_git_source_missing_pinned_commit_is_skipped(self, tmp_path: Path):
        repo = tmp_path / "vendor" / "musubi-tuner"
        self._init_git_source(repo, "seed")
        from mikazuki.engines.musubi.settings import resolve_install_source_root

        with pytest.raises(ValueError, match="未找到 musubi-tuner 源码"):
            resolve_install_source_root(tmp_path, None, FULL_SHA)

    def test_git_source_with_commit_available_is_accepted(self, tmp_path: Path):
        repo = tmp_path / "vendor" / "musubi-tuner"
        head = self._init_git_source(repo, "seed")
        from mikazuki.engines.musubi.settings import resolve_install_source_root

        result = resolve_install_source_root(tmp_path, None, head)
        assert result == repo.resolve()

    def test_installer_copies_snapshot_without_git(self, tmp_path: Path):
        _make_bundle(
            tmp_path,
            {"musubi-tuner": {
                "src/musubi_tuner/__init__.py": "",
                "pyproject.toml": "[project]\nname='x'\n",
                ".source_commit": FULL_SHA + "\n",
            }},
        )
        from mikazuki.engines.musubi.extension_state import default_layout
        from mikazuki.engines.musubi.installer import build_install_plan, copy_source_snapshot

        source = ensure_vendor_source(tmp_path, "musubi-tuner")
        layout = default_layout(tmp_path)
        plan = build_install_plan(source, layout, dry_run=False, source_commit=FULL_SHA)
        copy_source_snapshot(plan)
        assert (plan.target_source / "src" / "musubi_tuner").is_dir()
        assert (plan.target_source / ".source_commit").read_text(encoding="utf-8").strip() == FULL_SHA


class TestAnimaResolveViaBundle:
    def test_resolve_picks_snapshot_with_pinned_commit(self, tmp_path: Path):
        _make_bundle(tmp_path, {"anima_lora": {"train.py": "print(1)\n", ".source_commit": FULL_SHA + "\n"}})
        from mikazuki.engines.anima_fast.source_root import resolve_install_source_root

        result = resolve_install_source_root(tmp_path, None, FULL_SHA)
        assert result == (tmp_path / "vendor" / "anima_lora").resolve()

    def test_installer_copies_snapshot_without_git(self, tmp_path: Path):
        _make_bundle(tmp_path, {"anima_lora": {"train.py": "print(1)\n", ".source_commit": FULL_SHA + "\n"}})
        from mikazuki.engines.anima_fast.extension_state import ExtensionLayout
        from mikazuki.engines.anima_fast.installer import build_install_plan, copy_source_snapshot

        source = ensure_vendor_source(tmp_path, "anima_lora")
        layout = ExtensionLayout(tmp_path / "extensions" / "anima_lora")
        plan = build_install_plan(source, layout, dry_run=False, source_commit=FULL_SHA)
        copy_source_snapshot(plan)
        assert (plan.target_source / "train.py").is_file()
        assert (plan.target_source / ".source_commit").read_text(encoding="utf-8").strip() == FULL_SHA

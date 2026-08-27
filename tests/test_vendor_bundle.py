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


class TestSnapshotMatches:
    def test_prefix_tolerant(self, tmp_path: Path):
        (tmp_path / ".source_commit").write_text(FULL_SHA + "\n", encoding="utf-8")
        assert snapshot_matches(tmp_path, FULL_SHA)
        assert snapshot_matches(tmp_path, "8781981")
        assert snapshot_matches(tmp_path, FULL_SHA[:7])
        assert not snapshot_matches(tmp_path, "deadbeef")
        assert not snapshot_matches(tmp_path, "")


class TestMusubiResolveViaBundle:
    def test_resolve_picks_vendor_source_without_git(self, tmp_path: Path):
        _make_bundle(tmp_path, {"musubi-tuner": {"src/musubi_tuner/__init__.py": "", ".source_commit": FULL_SHA + "\n"}})
        from mikazuki.engines.musubi.settings import resolve_install_source_root

        result = resolve_install_source_root(tmp_path, None, FULL_SHA)
        assert result == (tmp_path / "vendor" / "musubi-tuner").resolve()

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

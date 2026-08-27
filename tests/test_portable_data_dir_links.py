"""Tests for portable SD-Trainer data directory layout helper."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "portable"))

from link_portable_data_dirs import (  # noqa: E402
    TRAINER_CANONICAL_DIR_NAMES,
    ensure_portable_data_dir,
    is_portable_layout,
    link_all_portable_data_dirs,
    resolve_portable_roots,
)


def _is_junction(path: Path) -> bool:
    if os.name != "nt":
        return path.is_symlink()
    import stat

    return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
def test_ensure_creates_inner_dir_and_outer_junction(tmp_path: Path):
    portable_root = tmp_path / "PortableRoot"
    trainer = portable_root / "SD-Trainer"
    trainer.mkdir(parents=True)
    (trainer / "gui.py").write_text("# test\n", encoding="utf-8")
    (portable_root / "python_embeded").mkdir()

    result = ensure_portable_data_dir(trainer, portable_root, "output", log=lambda *_: None)
    assert result == "linked-outer"
    assert (trainer / "output").is_dir()
    assert not _is_junction(trainer / "output")
    assert _is_junction(portable_root / "output")
    assert (portable_root / "output").resolve() == (trainer / "output").resolve()


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
def test_migrate_legacy_inner_junction_to_outer(tmp_path: Path):
    """Old layout: SD-Trainer/output -> ../output with data at portable root."""
    portable_root = tmp_path / "PortableRoot"
    trainer = portable_root / "SD-Trainer"
    trainer.mkdir(parents=True)
    (trainer / "gui.py").write_text("# test\n", encoding="utf-8")
    (portable_root / "python_embeded").mkdir()
    outer = portable_root / "output"
    outer.mkdir()
    (outer / "lora.safetensors").write_text("x", encoding="utf-8")

    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(trainer / "output"), str(outer)],
        check=True,
        capture_output=True,
    )

    result = ensure_portable_data_dir(trainer, portable_root, "output", log=lambda *_: None)
    assert result == "migrated-flip"
    assert (trainer / "output" / "lora.safetensors").is_file()
    assert _is_junction(portable_root / "output")
    assert (portable_root / "output").resolve() == (trainer / "output").resolve()


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
def test_migrate_outer_real_folder_into_trainer(tmp_path: Path):
    portable_root = tmp_path / "PortableRoot"
    trainer = portable_root / "SD-Trainer"
    trainer.mkdir(parents=True)
    (trainer / "gui.py").write_text("# test\n", encoding="utf-8")
    (portable_root / "python_embeded").mkdir()
    outer = portable_root / "sd-models"
    outer.mkdir()
    (outer / "marker.txt").write_text("ok", encoding="utf-8")

    result = ensure_portable_data_dir(trainer, portable_root, "sd-models", log=lambda *_: None)
    assert result == "migrated-outer-to-inner"
    assert (trainer / "sd-models" / "marker.txt").read_text(encoding="utf-8") == "ok"
    assert _is_junction(portable_root / "sd-models")


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
def test_migrate_merges_nonempty_dirs_and_preserves_name_conflicts(tmp_path: Path):
    portable_root = tmp_path / "PortableRoot"
    trainer = portable_root / "SD-Trainer"
    trainer.mkdir(parents=True)
    (trainer / "gui.py").write_text("# test\n", encoding="utf-8")
    (portable_root / "python_embeded").mkdir()
    inner = trainer / "output"
    inner.mkdir()
    (inner / "same.safetensors").write_text("inner", encoding="utf-8")
    (inner / "inner-only.safetensors").write_text("inner", encoding="utf-8")
    outer = portable_root / "output"
    outer.mkdir()
    (outer / "same.safetensors").write_text("outer", encoding="utf-8")
    (outer / "outer-only.safetensors").write_text("outer", encoding="utf-8")

    result = ensure_portable_data_dir(trainer, portable_root, "output", log=lambda *_: None)

    assert result == "migrated-outer-to-inner"
    assert (inner / "same.safetensors").read_text(encoding="utf-8") == "inner"
    assert (inner / "same.safetensors.portable-root").read_text(encoding="utf-8") == "outer"
    assert (inner / "inner-only.safetensors").is_file()
    assert (inner / "outer-only.safetensors").is_file()
    assert _is_junction(portable_root / "output")


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
def test_migrate_legacy_layout_after_portable_root_moves(tmp_path: Path):
    old_root = tmp_path / "OldRoot"
    trainer = old_root / "SD-Trainer"
    trainer.mkdir(parents=True)
    (trainer / "gui.py").write_text("# test\n", encoding="utf-8")
    (old_root / "python_embeded").mkdir()
    outer = old_root / "output"
    outer.mkdir()
    (outer / "lora.safetensors").write_text("x", encoding="utf-8")
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(trainer / "output"), str(outer)],
        check=True,
        capture_output=True,
    )

    portable_root = tmp_path / "MovedRoot"
    shutil.move(str(old_root), str(portable_root))
    trainer = portable_root / "SD-Trainer"

    result = ensure_portable_data_dir(trainer, portable_root, "output", log=lambda *_: None)
    assert result == "migrated-flip"
    assert (trainer / "output" / "lora.safetensors").is_file()
    assert _is_junction(portable_root / "output")
    assert (portable_root / "output").resolve() == (trainer / "output").resolve()


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
def test_relinks_canonical_outer_junction_after_portable_root_moves(tmp_path: Path):
    old_root = tmp_path / "OldRoot"
    trainer = old_root / "SD-Trainer"
    trainer.mkdir(parents=True)
    (trainer / "gui.py").write_text("# test\n", encoding="utf-8")
    (old_root / "python_embeded").mkdir()
    ensure_portable_data_dir(trainer, old_root, "output", log=lambda *_: None)
    (trainer / "output" / "lora.safetensors").write_text("x", encoding="utf-8")

    portable_root = tmp_path / "MovedRoot"
    shutil.move(str(old_root), str(portable_root))
    trainer = portable_root / "SD-Trainer"

    result = ensure_portable_data_dir(trainer, portable_root, "output", log=lambda *_: None)
    assert result == "linked-outer"
    assert (trainer / "output" / "lora.safetensors").is_file()
    assert _is_junction(portable_root / "output")
    assert (portable_root / "output").resolve() == (trainer / "output").resolve()


def test_is_portable_layout_detects_embedded_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # is_portable_layout is Windows-only by design; simulate nt for the layout check.
    monkeypatch.setattr("link_portable_data_dirs.os.name", "nt")
    portable_root = tmp_path / "PortableRoot"
    trainer = portable_root / "SD-Trainer"
    trainer.mkdir(parents=True)
    (trainer / "gui.py").write_text("# test\n", encoding="utf-8")
    (portable_root / "python_embeded").mkdir()
    assert is_portable_layout(trainer, portable_root) is True


def test_resolve_portable_roots_from_trainer_dir(tmp_path: Path):
    trainer = tmp_path / "SD-Trainer"
    trainer.mkdir()
    resolved_trainer, portable_root = resolve_portable_roots(trainer)
    assert resolved_trainer == trainer.resolve()
    assert portable_root == tmp_path.resolve()


def test_launcher_invokes_link_script():
    launcher = (ROOT / "scripts" / "portable" / "launch_portable.bat").read_text(
        encoding="utf-8"
    )
    assert "link_portable_data_dirs.py" in launcher


def test_build_script_creates_trainer_data_dirs():
    script = (ROOT / "build-scripts" / "build_portable.ps1").read_text(encoding="utf-8")
    assert "Join-Path $sdtDir $d" in script or 'Join-Path $sdtDir $d' in script
    assert "sd-models" in script
    assert "link_portable_data_dirs.py" in script


def test_canonical_dir_names_exclude_tagger_models():
    assert "tagger-models" not in TRAINER_CANONICAL_DIR_NAMES

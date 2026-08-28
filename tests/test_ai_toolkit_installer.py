"""ai-toolkit installer: source snapshot completeness (KNOWN_PITFALLS P7)."""

from pathlib import Path

from mikazuki.engines.ai_toolkit.extension_state import default_layout
from mikazuki.engines.ai_toolkit.installer import build_install_plan, copy_source_snapshot


def _fake_source(root: Path) -> Path:
    src = root / "upstream"
    (src / "toolkit").mkdir(parents=True)
    (src / "extensions_built_in").mkdir()
    (src / "run.py").write_text("", encoding="utf-8")
    (src / "info.py").write_text("software_meta = {}\n", encoding="utf-8")
    (src / "version.py").write_text("", encoding="utf-8")
    (src / "requirements_base.txt").write_text("", encoding="utf-8")
    (src / "dgx_requirements.txt").write_text("", encoding="utf-8")
    return src


def test_snapshot_includes_root_modules(tmp_path):
    src = _fake_source(tmp_path)
    layout = default_layout(tmp_path)
    copy_source_snapshot(build_install_plan(src, layout, dry_run=False))
    for name in ("run.py", "info.py", "version.py", "requirements_base.txt", "dgx_requirements.txt"):
        assert (layout.source / name).is_file(), name
    assert (layout.source / "toolkit").is_dir()
    assert (layout.source / "extensions_built_in").is_dir()
    # get_model.py iterates extensions/ — must exist even though upstream ships none
    assert (layout.source / "extensions").is_dir()

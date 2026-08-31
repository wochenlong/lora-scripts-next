"""ai-toolkit installer: source snapshot completeness (KNOWN_PITFALLS P7)."""

from pathlib import Path
from types import SimpleNamespace

from mikazuki.engines.ai_toolkit.extension_state import (
    STATE_BROKEN,
    STATE_INSTALLING,
    default_layout,
    read_extension_status,
    write_install_state,
)
from mikazuki.engines.ai_toolkit.installer import build_install_plan, copy_source_snapshot
from mikazuki.tasks import TaskStatus, tm


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


def test_status_reports_installing_before_runtime_files_exist(tmp_path, monkeypatch):
    """Installer writes `installing` before copying source/ or creating the
    venv; polling must not fall through to not_installed mid-install."""
    layout = default_layout(tmp_path)
    write_install_state(layout, STATE_INSTALLING, {"task_id": "task-1"}, "copying ai-toolkit source snapshot")
    assert not layout.source.exists()

    monkeypatch.setattr(tm, "tasks", {"task-1": SimpleNamespace(status=TaskStatus.RUNNING, metadata={})})
    status = read_extension_status(layout)

    assert status.state == STATE_INSTALLING
    assert status.facts["task_id"] == "task-1"


def test_status_installing_with_gone_task_reconciles_to_broken(tmp_path, monkeypatch):
    layout = default_layout(tmp_path)
    write_install_state(layout, STATE_INSTALLING, {"task_id": "task-1"})

    monkeypatch.setattr(tm, "tasks", {})
    status = read_extension_status(layout)

    assert status.state == STATE_BROKEN


def test_status_without_install_state_keeps_filesystem_behavior(tmp_path):
    layout = default_layout(tmp_path)
    layout.root.mkdir(parents=True)

    status = read_extension_status(layout)

    assert status.state == "not_installed"

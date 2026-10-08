"""ai-toolkit environment: platform-unsupported pin stripping (KNOWN_PITFALLS P5)."""

import sys
from pathlib import Path

from mikazuki.engines.ai_toolkit import environment
from mikazuki.engines.ai_toolkit.extension_state import (
    STATE_BROKEN,
    STATE_READY,
    default_layout,
    read_extension_status,
    write_install_state,
)


def test_prepare_requirements_strips_nested_pin(tmp_path, monkeypatch):
    # This is an ARM/Linux compatibility rule; make the test deterministic on Windows.
    monkeypatch.setattr(environment, "_needs_pin_strip", lambda: True)
    monkeypatch.setattr(environment, "requirements_file", lambda source_root: source_root / "dgx_requirements.txt")
    (tmp_path / "requirements_base.txt").write_text(
        "torch==2.11.0\ntorchcodec==0.9.1\nnumpy>=2,<3\n", encoding="utf-8"
    )
    (tmp_path / "dgx_requirements.txt").write_text(
        "-r requirements_base.txt\nscipy==1.16.0\n", encoding="utf-8"
    )
    out = environment.prepare_requirements(tmp_path, tmp_path / "work")
    assert out.name == ".dgx_requirements.platform-filtered.txt"
    top = out.read_text(encoding="utf-8")
    assert "scipy==1.16.0" in top
    assert "torchcodec" not in top
    included = Path(top.split("-r ", 1)[1].splitlines()[0])
    included_text = included.read_text(encoding="utf-8")
    assert "torchcodec" not in included_text
    assert "numpy>=2,<3" in included_text


def test_prepare_requirements_passthrough_without_match(tmp_path):
    (tmp_path / "requirements_base.txt").write_text("numpy>=2,<3\n", encoding="utf-8")
    out = environment.prepare_requirements(tmp_path, tmp_path / "work")
    assert out == tmp_path / "requirements_base.txt"


def test_prepare_requirements_passthrough_off_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(environment, "_needs_pin_strip", lambda: False)
    (tmp_path / "requirements_base.txt").write_text("torchcodec==0.9.1\n", encoding="utf-8")
    out = environment.prepare_requirements(tmp_path, tmp_path / "work")
    assert out == tmp_path / "requirements_base.txt"


def _make_installed_layout(root: Path):
    layout = default_layout(root)
    (layout.source / "toolkit").mkdir(parents=True)
    (layout.source / "extensions_built_in").mkdir()
    (layout.source / "run.py").write_text("", encoding="utf-8")
    (layout.source / "requirements_base.txt").write_text("", encoding="utf-8")
    layout.venv_python.parent.mkdir(parents=True)
    layout.venv_python.write_text("", encoding="utf-8")
    return layout


def _write_venv_cfg(layout, home: Path) -> None:
    cfg = layout.venv_python.parent.parent / "pyvenv.cfg"
    cfg.write_text(
        f"home = {home}\n"
        "include-system-site-packages = false\n"
        "version = 3.11.9\n"
        f"executable = {home / 'python.exe'}\n"
        f"command = {home / 'python.exe'} -m venv {layout.root / '.venv'}\n",
        encoding="utf-8",
    )


def _make_packaged_python(root: Path) -> Path:
    if sys.platform == "win32":
        python = root / ".python" / "cpython-3.11.11-windows-x86_64-none" / "python.exe"
    else:
        python = root / ".python" / "cpython-3.11.11-linux-x86_64-gnu" / "bin" / "python3"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return python


def test_status_relocates_stale_venv_home(tmp_path):
    layout = _make_installed_layout(tmp_path)
    _write_venv_cfg(layout, tmp_path / "old-location" / ".python" / "cpython-3.11")
    base = _make_packaged_python(tmp_path)
    write_install_state(layout, STATE_READY, {"audit": {"ok": True}})
    status = read_extension_status(layout)
    assert status.state == STATE_READY
    cfg = (layout.venv_python.parent.parent / "pyvenv.cfg").read_text(encoding="utf-8")
    assert f"home = {base.parent}" in cfg
    assert "old-location" not in cfg


def test_status_marks_broken_when_no_packaged_python(tmp_path):
    layout = _make_installed_layout(tmp_path)
    _write_venv_cfg(layout, tmp_path / "old-location" / ".python" / "cpython-3.11")
    write_install_state(layout, STATE_READY, {"audit": {"ok": True}})
    status = read_extension_status(layout)
    assert status.state == STATE_BROKEN
    assert "3.11" in status.reason


def test_status_leaves_healthy_venv_untouched(tmp_path):
    layout = _make_installed_layout(tmp_path)
    home = tmp_path / "system-python"
    home.mkdir()
    _write_venv_cfg(layout, home)
    _make_packaged_python(tmp_path)
    before = (layout.venv_python.parent.parent / "pyvenv.cfg").read_bytes()
    read_extension_status(layout)
    assert (layout.venv_python.parent.parent / "pyvenv.cfg").read_bytes() == before

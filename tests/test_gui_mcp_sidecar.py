"""gui.py MCP sidecar launch integration tests."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import gui


@pytest.fixture(autouse=True)
def _gui_args():
    gui.args = SimpleNamespace(port=28000, mcp_port=28002)
    yield
    del gui.args


def test_parser_has_mcp_flags():
    text = Path(gui.__file__).read_text(encoding="utf-8")
    assert '"--disable-mcp"' in text
    assert '"--mcp-port"' in text
    assert "default=28002" in text


def test_run_mcp_sidecar_skips_when_venv_missing(tmp_path, caplog):
    with patch.object(gui, "base_dir_path", return_value=tmp_path):
        assert gui.run_mcp_sidecar() is None


def test_run_mcp_sidecar_command(tmp_path):
    venv_python = tmp_path / "mcp" / ".venv" / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()

    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return None

    with patch.object(gui, "base_dir_path", return_value=tmp_path), patch.object(gui, "_popen", fake_popen):
        gui.run_mcp_sidecar()

    command = captured["command"]
    assert command[0] == str(venv_python)
    assert command[1:3] == ["-m", "next_trainer_mcp"]
    assert "--base-url" in command and "http://127.0.0.1:28000" in command
    # sidecar must stay loopback-only even though the GUI can --listen
    assert "--host" in command and command[command.index("--host") + 1] == "127.0.0.1"
    assert "--port" in command and command[command.index("--port") + 1] == "28002"


def test_mcp_port_reserved_in_launch_flow():
    text = Path(gui.__file__).read_text(encoding="utf-8")
    assert '"MCP sidecar"' in text
    assert "args.mcp_port = ensure_port_available(" in text
    assert '("MCP sidecar", mcp_process)' in text

"""setup_environment.py MCP sidecar install step tests (best-effort add-on)."""

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import setup_environment


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_environment, "_sd_trainer_dir", lambda: str(tmp_path))
    return tmp_path


def test_skips_when_mcp_dir_absent(fake_root):
    assert setup_environment.install_mcp_sidecar() is True


def test_skips_when_venv_already_installed(fake_root):
    venv_python = Path(setup_environment._mcp_sidecar_venv_python())
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()
    (fake_root / "mcp" / "pyproject.toml").parent.mkdir(exist_ok=True)
    (fake_root / "mcp" / "pyproject.toml").touch()
    with mock.patch.object(setup_environment.subprocess, "call") as call:
        assert setup_environment.install_mcp_sidecar() is True
    call.assert_not_called()


def test_venv_failure_is_non_fatal(fake_root, capsys):
    (fake_root / "mcp").mkdir()
    (fake_root / "mcp" / "pyproject.toml").touch()
    with mock.patch.object(setup_environment.subprocess, "call", return_value=1):
        assert setup_environment.install_mcp_sidecar() is False
    out = capsys.readouterr().out
    assert "不影响主程序" in out


def test_success_runs_venv_pip_and_probe(fake_root):
    (fake_root / "mcp").mkdir()
    (fake_root / "mcp" / "pyproject.toml").touch()
    calls = []

    def fake_call(cmd, **kwargs):
        calls.append(cmd)
        return 0

    with mock.patch.object(setup_environment.subprocess, "call", fake_call):
        assert setup_environment.install_mcp_sidecar() is True

    assert calls[0][1:3] == ["-m", "venv"]  # [sys.executable, -m, venv, dir]
    assert "pip" in calls[1] and str(fake_root / "mcp") in calls[1]
    assert "import next_trainer_mcp" in calls[2][-1]

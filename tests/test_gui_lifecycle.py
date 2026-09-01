from __future__ import annotations

import os
import subprocess
import sys
import time
import types
from pathlib import Path
from unittest import mock

import gui


class FakeProcess:
    def __init__(
        self, pid: int, *, running: bool = True, times_out: bool = False,
        wait_error: Exception | None = None
    ):
        self.pid = pid
        self.running = running
        self.times_out = times_out
        self.wait_error = wait_error
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        if self.wait_error is not None and not self.killed:
            raise self.wait_error
        if self.times_out and not self.killed:
            raise subprocess.TimeoutExpired(str(self.pid), timeout)
        self.running = False
        return 0

    def kill(self):
        self.killed = True


def test_legacy_tageditor_is_disabled_by_default():
    args = gui.parser.parse_args([])

    assert args.enable_legacy_tageditor is False


def test_helper_launchers_return_process_handles():
    process = FakeProcess(100)
    args = gui.parser.parse_args([])

    with mock.patch.object(gui, "args", args, create=True), mock.patch.object(
        gui.subprocess, "Popen", return_value=process
    ):
        assert gui.run_tensorboard() is process
        assert gui.run_train_monitor() is process


def test_linux_helper_processes_request_parent_death_signal():
    process = FakeProcess(107)

    with mock.patch.object(gui.sys, "platform", "linux"), \
            mock.patch.object(gui.os, "getpid", return_value=42), \
            mock.patch.object(gui.subprocess, "Popen", return_value=process) as popen:
        assert gui._popen(["helper"]) is process

    assert popen.call_args.args[0] == [
        gui.sys.executable,
        str(gui.base_dir_path() / "mikazuki" / "child_process.py"),
        "42",
        "helper",
    ]
    assert "preexec_fn" not in popen.call_args.kwargs


def test_non_linux_helper_processes_do_not_use_preexec():
    process = FakeProcess(108)

    with mock.patch.object(gui.sys, "platform", "win32"), \
            mock.patch.object(gui.subprocess, "Popen", return_value=process) as popen:
        assert gui._popen(["helper"]) is process

    assert "preexec_fn" not in popen.call_args.kwargs


def test_linux_child_exits_when_parent_is_killed_from_another_directory(tmp_path):
    if not sys.platform.startswith("linux"):
        return

    root = Path(__file__).resolve().parents[1]
    parent = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os,signal,subprocess,sys,time; from gui import _popen; "
                "signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM}); "
                "child=_popen([sys.executable,'-c','import time; time.sleep(60)'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
                "print(child.pid, flush=True); time.sleep(0.2); os._exit(0)"
            ),
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
        check=True,
    )
    child_pid = int(parent.stdout.strip())
    deadline = time.monotonic() + 3
    while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
        time.sleep(0.05)

    assert not Path(f"/proc/{child_pid}").exists()


def test_main_environment_does_not_require_gradio():
    root = Path(__file__).resolve().parents[1]
    requirements = (root / "requirements.txt").read_text(encoding="utf-8-sig")
    setup = (root / "setup_environment.py").read_text(encoding="utf-8")
    constraints = (root / "config/anima_fast_environment/main-constraints-cu130.txt").read_text(encoding="utf-8")

    assert not any(line.strip().startswith("gradio") for line in requirements.splitlines())
    assert '"diffusers", "gradio"' not in setup
    assert not any(line.strip().startswith("gradio") for line in constraints.splitlines())


def test_main_environment_declares_websockets_directly():
    root = Path(__file__).resolve().parents[1]
    requirements = (root / "requirements.txt").read_text(encoding="utf-8-sig")

    assert any(line.strip().startswith("websockets==") for line in requirements.splitlines())


def test_stop_child_processes_terminates_running_children():
    tensorboard = FakeProcess(101)
    monitor = FakeProcess(102)
    exited = FakeProcess(103, running=False)

    gui.stop_child_processes([
        ("TensorBoard", tensorboard),
        ("train monitor", monitor),
        ("exited", exited),
    ])

    assert tensorboard.terminated is True
    assert monitor.terminated is True
    assert exited.terminated is False
    assert tensorboard.killed is False
    assert monitor.killed is False


def test_stop_child_processes_kills_child_after_timeout():
    stuck = FakeProcess(104, times_out=True)

    gui.stop_child_processes([("TensorBoard", stuck)], timeout=0)

    assert stuck.terminated is True
    assert stuck.killed is True
    assert stuck.running is False


def test_stop_child_processes_kills_child_after_wait_error():
    stuck = FakeProcess(106, wait_error=OSError("wait failed"))

    gui.stop_child_processes([("TensorBoard", stuck)])

    assert stuck.killed is True
    assert stuck.running is False


def test_launch_cleans_up_helpers_when_server_fails():
    process = FakeProcess(105)
    args = gui.parser.parse_args([
        "--skip-prepare-environment",
        "--disable-train-monitor",
    ])
    uvicorn = types.SimpleNamespace(run=mock.Mock(side_effect=RuntimeError("server failed")))

    with mock.patch.object(gui, "args", args, create=True), \
            mock.patch.object(gui, "sanitize_embedded_deps"), \
            mock.patch.object(gui, "train_env_overrides", return_value={}), \
            mock.patch.object(gui, "ensure_requirements_installed"), \
            mock.patch.object(gui, "ensure_port_available", side_effect=lambda port, *_args, **_kwargs: port), \
            mock.patch.object(gui, "run_tensorboard", return_value=process), \
            mock.patch("mikazuki.china_hub.enable_china_hub", return_value=False), \
            mock.patch("mikazuki.update_check.local_version", return_value="test"), \
            mock.patch.dict(sys.modules, {"uvicorn": uvicorn}):
        try:
            gui.launch()
        except RuntimeError as error:
            assert str(error) == "server failed"
        else:
            raise AssertionError("launch should propagate the server failure")

    assert process.terminated is True
    assert process.running is False
